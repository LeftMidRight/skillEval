"""Generate downstream.py with fact/indicator as direct comparison."""
import re
import sys
sys.path.insert(0, 'D:/Code/bytedanceCamp')

TARGET = 'D:/Code/bytedanceCamp/evaluation/module3/downstream.py'
with open(TARGET, 'r', encoding='utf-8') as f:
    original = f.read()

# Change docstring
original = original.replace(
    '全部使用 LLM-as-Judge：\n- fact: LLM 根据 LAS markdown 提取指定科目数值\n- indicator: LLM 根据 LAS markdown 计算财务指标\n- reasoning: LLM 根据 LAS markdown + 条件做逻辑推理\n\n所有任务结果与 XBRL 真值对比。',
    '评测方法 (v3):\n- fact / indicator: 直接数值对比, 从 LAS markdown 表格中定位科目, 与 XBRL GT 对比\n- reasoning: LLM-as-Judge (需逻辑推理, 无法直接数值对比)\n\n所有任务结果与 XBRL 真值对比。'
)

# Remove FACT_PROMPT and INDICATOR_PROMPT
original = re.sub(r'FACT_PROMPT = """[^"]*"""[^"]*"""', 'FACT_PROMPT = ""  # deprecated, using direct table comparison', original, flags=re.DOTALL)
# Simpler: just replace known strings

print('Phase 1 done')
with open(TARGET, 'w', encoding='utf-8') as f:
    f.write(original)
print('Written')
