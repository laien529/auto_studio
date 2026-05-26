from __future__ import annotations

import json
from pathlib import Path


def build_prompt(root: Path, topic: str, column: str, angle: str, context: str = "") -> str:
    tpl = (root / "prompts" / "content_prompt.txt").read_text(encoding="utf-8")
    return (
        tpl.replace("{topic}", topic)
        .replace("{column}", column)
        .replace("{angle}", angle)
        .replace("{context}", context or "无")
    )


def load_settings(root: Path) -> dict:
    try:
        return json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def generate_openai(root: Path, topic: str, column: str, angle: str, context: str = "", model: str | None = None) -> dict:
    from openai import OpenAI

    if not model:
        settings = load_settings(root)
        model = settings.get("default_model_openai", "gpt-4.1-mini")

    client = OpenAI()
    prompt = build_prompt(root, topic, column, angle, context)

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.65,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def generate_ollama(root: Path, topic: str, column: str, angle: str, context: str = "", model: str | None = None) -> dict:
    from langchain_ollama import ChatOllama

    settings = load_settings(root)
    if not model:
        model = settings.get("default_model_ollama", "qwen2.5vl")

    import os
    num_cores = os.cpu_count() or 4
    num_threads = settings.get("ollama_num_thread", max(1, num_cores // 2))
    num_ctx = settings.get("ollama_num_ctx", 2048)

    prompt = build_prompt(root, topic, column, angle, context)
    llm = ChatOllama(model=model, temperature=0.65, num_ctx=num_ctx, num_thread=num_threads)
    resp = llm.invoke(prompt)
    text = resp.content
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("模型没有输出合法JSON。")

    # Unload the model to free memory
    try:
        print(f"  Unloading text model ({model}) to free memory...")
        import ollama
        client = ollama.Client()
        client.chat(model=model, keep_alive=0)
    except Exception as e:
        print(f"  Warning: Failed to unload text model: {e}")

    return json.loads(text[start:end + 1])


def save_content(root: Path, data: dict, name: str) -> Path:
    out = root / "outputs" / "content" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
