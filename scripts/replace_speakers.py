#!/usr/bin/env python3
"""
replace_speakers.py - 批次替換 Google Doc 中的 [Speaker N] 佔位符

用法：
    uv run scripts/replace_speakers.py --doc-id <DOC_ID> \
        --mapping "Speaker 1=Fredrick" "Speaker 2=Frank" "Speaker 3=Mark"

也可直接傳入 Google Doc 連結：
    uv run scripts/replace_speakers.py \
        --doc-id https://docs.google.com/document/d/XXXXX/edit \
        --mapping "Speaker 1=Fredrick" "Speaker 2=Frank"
"""

import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent


def parse_doc_id(raw: str) -> str:
    """從完整 URL 或 doc ID 字串中提取 doc ID"""
    m = re.search(r"/document/d/([a-zA-Z0-9_-]+)", raw)
    if m:
        return m.group(1)
    return raw.strip()


def replace_in_doc(doc_id: str, mapping: dict[str, str]):
    """使用 Google Docs API 的 replaceAllText 批次替換佔位符"""
    # 借用主腳本的 get_google_credentials
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "generate_meeting_notes",
        SKILL_DIR / "scripts" / "generate_meeting_notes.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    spec.loader.exec_module(mod)  # type: ignore

    from googleapiclient.discovery import build
    creds = mod.get_google_credentials()
    docs = build("docs", "v1", credentials=creds)

    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": f"[{speaker}]", "matchCase": True},
                "replaceText": name,
            }
        }
        for speaker, name in mapping.items()
    ]

    result = docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests},
    ).execute()

    replaced = sum(
        r.get("replaceAllText", {}).get("occurrencesChanged", 0)
        for r in result.get("replies", [])
    )
    print(f"✅ 完成：共替換 {replaced} 處")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="替換 Google Doc 中的 Speaker 佔位符")
    parser.add_argument(
        "--doc-id", required=True,
        help="Google Doc ID 或完整連結",
    )
    parser.add_argument(
        "--mapping", nargs="+", required=True,
        metavar="SPEAKER=NAME",
        help='替換對應，例："Speaker 1=Fredrick" "Speaker 2=Frank"',
    )
    args = parser.parse_args()

    doc_id = parse_doc_id(args.doc_id)

    mapping = {}
    for item in args.mapping:
        if "=" not in item:
            print(f"❌ 格式錯誤（需含 =）：{item}")
            sys.exit(1)
        speaker, name = item.split("=", 1)
        mapping[speaker.strip()] = name.strip()

    print(f"📄 Doc ID：{doc_id}")
    for speaker, name in mapping.items():
        print(f"   [{speaker}] → {name}")
    print()

    replace_in_doc(doc_id, mapping)


if __name__ == "__main__":
    main()
