# Draft bug report for Prime Intellect — INTELLECT-3.1 returns HTTP 500 on all chat-completions requests

**Status: DRAFT — not posted. Review before sending.**

Suggested venues: Prime Discord support channel and/or [PrimeIntellect-ai/prime-rl](https://github.com/PrimeIntellect-ai/prime-rl) GitHub issues. Discord first is probably faster. The two versions below trade detail for venue norms — pick whichever, or merge.

---

## Short version (Discord-style)

> Hi — `PrimeIntellect/INTELLECT-3.1` on the inference router returns HTTP 500 `Internal Server Error` for every request I've tried (~1.3s time-to-fail, so it's a fast rejection, not a timeout). The sibling `prime-intellect/intellect-3` works fine on the same key + endpoint. Other models on the router (sonnet-4.6, opus-4.7, gpt-5.2, deepseek-r1, gemini-2.5-pro, qwen3-30b) all work too.
>
> I tried: standard call, `stream:true`, `max_tokens` from default to 8192, `temperature=0`, system-only message, minimal `{"messages":[{"role":"user","content":"hi"}]}`. All HTTP 500 with the same body.
>
> Sample failing request_ids (all `9f2c…-KUL`):
> - `9f2ce815ae9811c9-KUL` (inference_id `req_68ee7044418b45828b288cf0a9e7269c`)
> - `9f2ce857cb345348-KUL` (stream:true)
> - `9f2ceb0e9ac0454a-KUL` (minimal payload)
>
> Lowercase / hyphenated ID variants (`primeintellect/intellect-3.1`, `prime-intellect/intellect-3.1`) return 404 `model_not_found`, so `PrimeIntellect/INTELLECT-3.1` is the only registered name.
>
> Happy to share more request_ids or rerun anything that helps. Context: I'm building a verifiers env and was running multi-model comparison; INTELLECT-3.1 is the only one returning 500.

---

## Long version (GitHub issue-style)

### Summary

`PrimeIntellect/INTELLECT-3.1` on `https://api.pinference.ai/api/v1/chat/completions` returns HTTP 500 `Internal Server Error` for every request configuration I've tried, including a payload as minimal as `{"model":"PrimeIntellect/INTELLECT-3.1","messages":[{"role":"user","content":"hi"}]}`. The sibling model `prime-intellect/intellect-3` works correctly through the same endpoint and the same API key. This appears to be specific to `INTELLECT-3.1` server-side, not a client-side parsing/format issue.

### Environment

- Endpoint: `https://api.pinference.ai/api/v1/chat/completions`
- Auth: `Bearer pit_…` (personal account)
- Date: 2026-04-27
- prime CLI version: 0.5.71

### Reproduction

```bash
curl -sS -w '\nHTTP=%{http_code}\nTIME=%{time_total}s\n' \
  -X POST https://api.pinference.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $PRIME_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"PrimeIntellect/INTELLECT-3.1","messages":[{"role":"user","content":"hi"}]}'
```

Response:

```
HTTP=500
TIME=1.288653s
{"error":{"message":"Internal Server Error","type":"server_error","param":null,"code":"server_error"},"request_id":"9f2ceb0e9ac0454a-KUL","inference_id":"req_5ab3c4d480d44974ac5b57abf6ea4013"}
```

### Configurations tested (all returned HTTP 500)

| Variant | request_id |
|---|---|
| Standard call: `messages=[{role:user, content:"What is 2+2?"}], max_tokens=100` | `9f2ce815ae9811c9-KUL` (`req_68ee7044418b45828b288cf0a9e7269c`) |
| `stream:true` (SSE) | `9f2ce857cb345348-KUL` (`req_daccf25eb7b847388dead905d7683170`) |
| `max_tokens=4096` | `9f2ce82fb95611c9-KUL` (`req_59d52ed0e50c4323972451930e128091`) |
| System-only: `messages=[{role:system, content:"You are a helpful assistant."}]` | `9f2ce83818431be4-KUL` (`req_c6fd229d850f4aa88e4af92de0fd8106`) |
| `temperature=0, top_p=1.0` | `9f2ce8408e53ee09-KUL` (`req_cdfaac84a12f4c9da24257b82b8f18c6`) |
| `max_tokens=8192, temperature=0` (reasoning-model budget) | `9f2ceb0648145e23-KUL` (`req_30dd6f57118347058b0884c3e8a12f75`) |
| Minimal: `messages=[{role:user, content:"hi"}]` | `9f2ceb0e9ac0454a-KUL` (`req_5ab3c4d480d44974ac5b57abf6ea4013`) |

Time-to-fail is consistently ~1.3-1.5s, which suggests a fast upstream rejection rather than a runaway-inference timeout.

### Model-ID variants

| Variant | HTTP | Body |
|---|---|---|
| `PrimeIntellect/INTELLECT-3.1` | **500** | `server_error` |
| `primeintellect/intellect-3.1` | 404 | `model_not_found` |
| `prime-intellect/intellect-3.1` (hyphenated) | 404 | `model_not_found` |
| `prime-intellect/intellect-3` (sibling, no `.1`) | 200 | Works correctly |

### Sibling success case for contrast

The sibling `prime-intellect/intellect-3` with the same minimal payload returns:

```json
{
  "id": "9f2ceb16cc3eb2e8-KUL",
  "model": "prime-intellect/intellect-3",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "<125-char answer>",
      "reasoning": "<652-char chain-of-thought>",
      ...
    },
    "finish_reason": "stop"
  }],
  "usage": {"input_tokens": 10, "output_tokens": 188, "cost": 0.0002}
}
```

Same key, same endpoint, same payload structure — only the model ID differs.

### Impact

I'm building a public verifiers environment and was running INTELLECT-3.1 as one of eight models in a multi-model benchmark comparison. The other seven (Anthropic, OpenAI, Google, DeepSeek, Qwen, INTELLECT-3) all work. Currently I have to publish the env with INTELLECT-3.1 listed as "broken at provider, pending fix" — happy to re-run it once the model is back.

### Suspicion

INTELLECT-3.1 is described as a continued-training of INTELLECT-3 with `--reasoning-parser deepseek_r1`. If the reasoning-parser plumbing on the inference side hasn't been wired up the same way as for INTELLECT-3, every request might fail before any tokens are generated. (The 1.3s time-to-fail and "Internal Server Error" body — rather than 200 with empty content — suggest backend crash on init, not generation timeout.)

Happy to provide more request_ids, rerun any variant, or coordinate a test once a fix is staged.
