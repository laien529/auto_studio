\
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


def generate_openai(root: Path, topic: str, column: str, angle: str, context: str = "", model: str = "gpt-4.1-mini") -> dict:
    from openai import OpenAI

    client = OpenAI()
    prompt = build_prompt(root, topic, column, angle, context)

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.65,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def generate_ollama(root: Path, topic: str, column: str, angle: str, context: str = "", model: str = "qwen3:14b") -> dict:
    from langchain_ollama import ChatOllama

    prompt = build_prompt(root, topic, column, angle, context)
    llm = ChatOllama(model=model, temperature=0.65)
    resp = llm.invoke(prompt)
    text = resp.content
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("模型没有输出合法JSON。")
    return json.loads(text[start:end + 1])


def save_content(root: Path, data: dict, name: str) -> Path:
    out = root / "outputs" / "content" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
