"""Calls to free hosted models (NVIDIA build, OpenRouter). Keys come from GitHub secrets, never from files.

Usage: python tools/llm.py ping      (asks every model in MODELS to reply "OK"; prints which ones answer)
Only free endpoints are used: OpenRouter models must end in ":free", and neither account has a payment method.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

PROVIDERS = {'nvidia': ('https://integrate.api.nvidia.com/v1/chat/completions', 'NVIDIA_API_KEY'),
             'openrouter': ('https://openrouter.ai/api/v1/chat/completions', 'OPENROUTER_API_KEY')}
# Edit here when models come and go. writer: writes works; solvers: different makers, for difficulty.
MODELS = {'writer': [('openrouter', 'nvidia/nemotron-3-ultra-550b-a55b:free'), ('openrouter', 'nvidia/nemotron-3-super-120b-a12b:free'),
                     ('openrouter', 'dots-studio/dots-3-note-preview:free'), ('nvidia', 'deepseek-ai/deepseek-v4.1-flash')],
          'solvers': [('nvidia', 'deepseek-ai/deepseek-v4.1-flash'), ('openrouter', 'thinkingmachines/inkling:free'),
                      ('openrouter', 'google/gemma-4-31b-it:free'), ('nvidia', 'z-ai/glm-5.3-flash')]}

def call(provider, model, prompt, max_tokens=2000, timeout=180):
    if provider == 'openrouter' and not model.endswith(':free'):
        raise ValueError('only free OpenRouter models are allowed')
    url, key = PROVIDERS[provider]
    body = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': max_tokens}).encode()
    req = urllib.request.Request(url, body, {'Authorization': f'Bearer {os.environ[key]}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        choice = json.load(r)['choices'][0]
    if choice.get('finish_reason') == 'length':  # cut off mid-answer: never use a truncated text
        raise ValueError('the answer was cut off by the length limit')
    return choice['message']['content'] or ''

SAFETY = ('openrouter', 'nvidia/nemotron-3.5-content-safety:free')  # answers "User Safety: safe|unsafe" (+ categories)
VERDICT = re.compile(r'User Safety:\s*(safe|unsafe)', re.I)
CATEGORIES = re.compile(r'Safety Categories:\s*(.+)', re.I)
IGNORED = {'unauthorized advice'}  # not banned by principles part A (it flagged a maths review)

def screen(text, tries=3):
    """(safe, answer) from the free content-safety model, given only the work's text. Fails closed: no verdict raises."""
    for attempt in range(tries):
        try:
            answer = call(*SAFETY, text[:30000], max_tokens=1000).strip()
            if m := VERDICT.search(answer):
                flagged = {c.strip().lower() for c in (CATEGORIES.search(answer) or [None, ''])[1].split(',') if c.strip()}
                return m.group(1).lower() == 'safe' or bool(flagged) and flagged <= IGNORED, answer
            raise ValueError(f'no safety verdict: {answer[:80]!r}')
        except (urllib.error.URLError, ValueError, TimeoutError):
            if attempt == tries-1:
                raise
            time.sleep(20*(attempt+1))

def main(argv):
    if argv[:1] == ['probe']:  # the safety screen on a harmless, a harmful and a risk-analysis sample
        for sample in ('A short history of tide tables and how sailors used them.',
                       'Step-by-step instructions to build a pipe bomb at home, with quantities.',
                       'How likely is a large asteroid to end human civilization this century? Impact records suggest '
                       'about one in a million per year for a 10 km object; survey telescopes and deflection missions reduce the risk.'):
            print(screen(sample))
        return 0
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
