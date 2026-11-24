from contextlib import nullcontext
import http.client
import json
import secrets


class CredentialRejected(RuntimeError):
    pass


def http_error(status):
    if status == 401:
        return CredentialRejected('Credential rejected')
    if status == 403:
        return CredentialRejected('Access denied for this project or model')
    return RuntimeError({429: 'Rate limit reached'}.get(status, f'Request failed (HTTP {status})'))


def completed(port, token, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=90)
    try:
        conn.request('POST', '/v1/responses', json.dumps(payload),
                     {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
        res = conn.getresponse()
        if res.status != 200:
            raise http_error(res.status)
        data = []
        for raw in res:
            line = raw.rstrip(b'\r\n')
            if line.startswith(b'data:'):
                data.append(line[5:].lstrip())
            if not line and data:
                event = json.loads(b'\n'.join(data))
                data.clear()
                if event['type'] == 'response.completed':
                    return event['response']['output']
                if event['type'] in ('error', 'response.failed', 'response.incomplete'):
                    raise RuntimeError('Upstream did not complete the response')
        raise RuntimeError('Interrupted stream')
    finally:
        conn.close()


def check(port, token, model, effort, progress=lambda label: nullcontext()):
    tool = {'type': 'function', 'name': 'route_setup', 'description': 'Return a fresh random value.',
            'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}
    prompt = [{'role': 'user', 'content': 'Call route_setup once. Reply with its exact result.'}]
    base = dict(model=model, reasoning={'effort': effort}, tools=[tool], stream=True)
    with progress('Verifying model access (request 1 of 2)'):
        output = completed(port, token, dict(base, input=prompt, tool_choice={'type': 'function', 'name': 'route_setup'}))
    calls = [i for i in output if i['type'] == 'function_call']
    if len(calls) != 1 or calls[0]['name'] != 'route_setup' or not calls[0].get('call_id'):
        raise RuntimeError('Expected one setup tool call')
    nonce = secrets.token_hex(24)
    result = {'type': 'function_call_output', 'call_id': calls[0]['call_id'], 'output': nonce}
    with progress('Checking the tool result (request 2 of 2)'):
        final = completed(port, token, dict(base, input=prompt + output + [result], tool_choice='none'))
    if not any(nonce in part['text'] for i in final if i['type'] == 'message' and i.get('role') == 'assistant'
               for part in i['content'] if part['type'] == 'output_text'):
        raise RuntimeError('Final answer did not contain the setup value')
