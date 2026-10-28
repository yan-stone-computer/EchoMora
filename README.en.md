# EchoMora

### A group-chat AI companion that remembers, fades, and knows its boundaries.

EchoMora is a local-first reference architecture for layered memory, GraphRAG, per-user relationship state, soft forgetting, and optional DeepSeek inference. The demo has no third-party Python dependencies and works fully offline.

![EchoMora cover](https://cdn.jsdelivr.net/gh/yan-stone-computer/EchoMora@main/docs/assets/cover.png)

## Why another memory demo?

Long context solves "can the model see it?" It does not solve "should this be recalled for this person, in this conversation, at this cost?"

EchoMora makes that decision observable:

- recent chat stays in a bounded working window;
- durable facts become episodic vector memories;
- stable relationships become versioned graph assertions;
- affect is isolated per user and only changes tone;
- low-importance memories fade through soft suppression;
- other users' private memories are blocked before ranking;
- DeepSeek can be enabled, but an offline engine keeps the loop runnable.

## Quick start

Requires Python 3.10+. No API key, package install, or database server.

```bash
git clone https://github.com/yan-stone-computer/EchoMora.git
cd EchoMora
python -m echomora --open
```

Send:

```text
Please remember: I do not eat sweets and I am cutting fat.
```

Then:

```text
Why do you remember that I avoid sweets?
```

The inspector shows the actual recall score, graph hit, recency, and whether the memory was softly forgotten.

Architecture and the full Chinese tutorial live in [docs/architecture.zh-CN.md](docs/architecture.zh-CN.md) and [docs/tutorial.zh-CN.md](docs/tutorial.zh-CN.md).

![Interactive demo](https://cdn.jsdelivr.net/gh/yan-stone-computer/EchoMora@main/docs/assets/demo.png)

## Architecture

![Architecture](https://cdn.jsdelivr.net/gh/yan-stone-computer/EchoMora@main/docs/assets/architecture.png)

```text
message
  -> append-only event log + short-term window
  -> structured extraction
  -> vector memory + versioned graph + per-user affect
  -> visibility gate
  -> weighted recall + MMR + Top-N
  -> bounded prompt
  -> DeepSeek or offline fallback
```

## DeepSeek

```bash
cp .env.example .env
```

Set `DEEPSEEK_API_KEY`, then run `python -m echomora --open`. Failed API calls fall back to the local engine.

## Production boundary

This is an inspectable demo, not a turnkey production memory service. Replace the hashed lexical embedding with a multilingual embedding model, move recall to a vector index, make extraction asynchronous, and add tenant isolation, content review, retention, and deletion workflows before deployment.

MIT licensed.

