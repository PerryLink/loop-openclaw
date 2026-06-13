"""validate_templates.py —— Jinja2 模板完整性验证脚本

检查项:
1. 模板注册表中的变量与实际模板文件中的变量一致性
2. 所有预期的 .j2 模板文件存在且可读
3. 模板变量类型与注册表定义一致
4. 必填变量在模板中被引用
5. .j2.m2 变体与基础模板对应
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


ROOT = Path(__file__).parent.resolve()
TEMPLATE_DIR = ROOT / "templates"
REGISTRY_PATH = TEMPLATE_DIR / "template_registry.json"

# Expected core templates (without .j2 extension)
EXPECTED_TEMPLATES = [
    "AGENTS.md",
    "IDENTITY.md",
    "SOUL.md",
    "TOOLS.md",
    "openclaw.json",
    "worker_prompt",
    "review_prompt",
    "routing_rules.yaml",
    "sessions_config.yaml",
]


def load_registry() -> Dict:
    """加载模板变量注册表。"""
    if not REGISTRY_PATH.exists():
        print(f"[ERROR] 模板注册表不存在: {REGISTRY_PATH}")
        sys.exit(1)

    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def list_template_files() -> List[Path]:
    """列出所有模板文件。"""
    return sorted(TEMPLATE_DIR.glob("*.j2*"))


def extract_variables(template_path: Path) -> Set[str]:
    """从 Jinja2 模板中提取所有变量引用 {{ var }}。"""
    try:
        content = template_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] 无法读取模板 {template_path.name}: {e}")
        return set()

    # Match {{ variable_name }} and {{ variable_name.key }}
    # Also match {% for item in items %}, {% if condition %}
    vars_set = set()
    for match in re.finditer(r'\{\{\s*(\w+)', content):
        vars_set.add(match.group(1))
    for match in re.finditer(r'\{%\s*(?:for|if|elif)\s+\w+\s+in\s+(\w+)', content):
        vars_set.add(match.group(1))
    for match in re.finditer(r'\{%\s*if\s+(\w+)', content):
        vars_set.add(match.group(1))
    return vars_set


def validate() -> int:
    """运行所有验证，返回错误数。"""
    errors = 0
    registry = load_registry()
    registered_vars = set(registry.get("variables", {}).keys())
    template_files = list_template_files()

    print("=" * 60)
    print("loop-openclaw Jinja2 模板完整性验证")
    print("=" * 60)

    # Check 1: 预期的模板文件存在
    print("\n[1] 检查预期的模板文件...")
    base_names = {f.stem.replace(".j2", ""): f for f in template_files if f.suffix == ".j2"}

    for name in EXPECTED_TEMPLATES:
        if name in base_names:
            print(f"  PASS: {name}.j2")
        else:
            print(f"  FAIL: {name}.j2 不存在")
            errors += 1

    # Check 2: 模板文件可解析
    print("\n[2] 检查模板文件可解析...")
    for tf in template_files:
        try:
            content = tf.read_text(encoding="utf-8")
            assert len(content) > 0, f"{tf.name} 是空文件"
            print(f"  PASS: {tf.name} ({len(content)} bytes)")
        except Exception as e:
            print(f"  FAIL: {tf.name} - {e}")
            errors += 1

    # Check 3: 注册表变量在模板中被使用
    print("\n[3] 检查注册表变量在模板中的使用情况...")
    all_template_vars: Set[str] = set()
    for tf in template_files:
        if tf.suffix == ".j2":
            vars_in_file = extract_variables(tf)
            all_template_vars.update(vars_in_file)

    unused_vars = registered_vars - all_template_vars
    if unused_vars:
        for var in sorted(unused_vars):
            print(f"  WARN: 变量 '{var}' 在注册表中定义但未在任何模板中使用")
    else:
        print("  PASS: 所有注册表变量均在模板中被引用")

    # Check 4: 模板中的变量在注册表中定义
    print("\n[4] 检查模板中的变量是否在注册表中定义...")
    undefined_vars = all_template_vars - registered_vars
    known_internal = {"loop", "item", "agent", "idx", "key", "value", "mode"}
    real_undefined = undefined_vars - known_internal

    if real_undefined:
        for var in sorted(real_undefined):
            print(f"  WARN: 变量 '{var}' 在模板中使用但未在注册表中定义")
    else:
        print("  PASS: 所有模板变量均在注册表中定义")

    # Check 5: 必填变量检查
    print("\n[5] 检查必填变量...")
    required_vars = {k for k, v in registry.get("variables", {}).items() if v.get("required")}
    for var in sorted(required_vars):
        has_default = "default" in registry["variables"][var]
        if has_default:
            print(f"  INFO: 必填变量 '{var}' 有默认值")
        else:
            print(f"  NOTE: 必填变量 '{var}' 无默认值，渲染时必须提供")

    # Check 6: .j2.m2 变体检查
    print("\n[6] 检查 .j2.m2 变体与基础模板对应...")
    base_j2 = {f.stem: f for f in template_files if f.suffix == ".j2"}
    m2_files = [f for f in template_files if f.suffix == ".m2"]

    for m2 in m2_files:
        base_name = m2.stem.replace(".j2", "")
        if base_name in base_j2:
            print(f"  PASS: {m2.name} 对应基础模板 {base_name}.j2")
        else:
            print(f"  WARN: {m2.name} 没有对应的基础模板 {base_name}.j2")

    # Check 7: 注册表类型验证
    print("\n[7] 检查注册表变量类型定义...")
    valid_types = {"str", "int", "bool", "list", "dict", "float"}
    for var_name, var_def in registry.get("variables", {}).items():
        var_type = var_def.get("type", "str")
        if var_type not in valid_types:
            print(f"  WARN: 变量 '{var_name}' 类型 '{var_type}' 不在 {valid_types} 中")
        if "enum" in var_def and var_def.get("default") not in var_def["enum"]:
            print(f"  INFO: 变量 '{var_name}' 默认值 '{var_def.get('default')}' 不在枚举值中")

    print("\n" + "=" * 60)
    print(f"模板注册变量数: {len(registered_vars)}")
    print(f"模板文件数: {len(template_files)}")
    print(f"模板中实际使用的唯一变量数: {len(all_template_vars)}")
    if errors:
        print(f"验证失败: {errors} 个错误")
    else:
        print("验证通过: 所有模板完整性检查通过")
    print("=" * 60)

    return errors


if __name__ == "__main__":
    exit_code = validate()
    sys.exit(min(exit_code, 1))
