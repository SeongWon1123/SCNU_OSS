"""LLM 패키지 — SPEC.md §7. 탐지는 정적분석, 해설·문서 생성만 LLM(절대규칙 1).

LLM 실패는 스캔 실패가 아니다(절대규칙 5): 이 패키지의 모든 run()은 예외를
삼키고 meta.llm.status='skipped'로 끝낸다.
"""
