"""Calls to free hosted models (NVIDIA build, OpenRouter). Keys come from GitHub secrets, never from files.

Usage: python tools/llm.py ping      (asks every model in MODELS to reply "OK"; prints which ones answer)
Only free endpoints are used: OpenRouter models must end in ":free", and neither account has a payment method.
"""
import json
import os
import sys
import urllib.error
import urllib.request

PROVIDERS = {'nvidia': ('https://integrate.api.nvidia.com/v1/chat/completions', 'NVIDIA_API_KEY'),
             'openrouter': ('https://openrouter.ai/api/v1/chat/completions', 'OPENROUTER_API_KEY')}
# Edit here when models come and go. writer: writes works; solvers: different makers, for difficulty.
MODELS = {'writer': [('openrouter', 'nvidia/nemotron-3-ultra-550b-a55b:free'), ('nvidia', 'deepseek-ai/deepseek-v4.1-flash')],
          'solvers': [('nvidia', 'deepseek-ai/deepseek-v4.1-flash'), ('openrouter', 'thinkingmachines/inkling:free'),
                      ('openrouter', 'google/gemma-4-31b-it:free'), ('nvidia', 'z-ai/glm-5.3-flash')]}

def call(provider, model, prompt, max_tokens=2000, timeout=180):
    if provider == 'openrouter' and not model.endswith(':free'):
        raise ValueError('only free OpenRouter models are allowed')
    url, key = PROVIDERS[provider]
    body = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': max_tokens}).encode()
    req = urllib.request.Request(url, body, {'Authorization': f'Bearer {os.environ[key]}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)['choices'][0]['message']['content'] or ''

def main(argv):
    if argv[:1] != ['ping']:
        print(__doc__); return 1
    for provider, model in dict.fromkeys(m for ms in MODELS.values() for m in ms):
        try:
            reply = call(provider, model, 'Reply with the single word OK.', max_tokens=300).strip()
            print(f'OK    {provider:10} {model}: {reply[:40]!r}')
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
            detail = exc.read().decode()[:160] if isinstance(exc, urllib.error.HTTPError) else str(exc)[:160]
            print(f'FAIL  {provider:10} {model}: {detail}')
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
