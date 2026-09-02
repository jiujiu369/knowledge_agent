import ast
from pathlib import Path


EXCLUDED_DIRS = {".git", ".pytest_cache", ".tmp", ".venv", "__pycache__"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _python_files() -> list[Path]:
    """获取项目内需要检查的 Python 源文件。

    :return: 返回排除虚拟环境、缓存和临时目录后的 Python 文件路径列表。
    """
    return [
        path
        for path in PROJECT_ROOT.rglob("*.py")
        if not any(
            part in EXCLUDED_DIRS or part.startswith(".venv")
            for part in path.relative_to(PROJECT_ROOT).parts
        )
    ]


def test_python_files_excludes_virtual_environment_prefixes() -> None:
    """验证带 ``.venv`` 前缀的本地虚拟环境不会被当作项目源码扫描。

    :return: 无返回值；扫描结果包含虚拟环境内 Python 文件时由断言报错。
    """
    assert not any(
        part.startswith(".venv")
        for path in _python_files()
        for part in path.relative_to(PROJECT_ROOT).parts
    )


def _function_arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """提取函数需要在 Docstring 中说明的参数名称。

    :param node: 待检查的同步函数或异步函数语法树节点。
    :return: 返回除 ``self`` 和 ``cls`` 外的全部位置、关键字及可变参数名称。
    """
    arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    names = [argument.arg for argument in arguments if argument.arg not in {"self", "cls"}]
    if node.args.vararg:
        names.append(node.args.vararg.arg)
    if node.args.kwarg:
        names.append(node.args.kwarg.arg)
    return names


def test_all_project_functions_have_chinese_rest_docstrings() -> None:
    """验证项目内所有函数均包含中文 reStructuredText Docstring。

    :return: 无返回值；缺失中文说明、参数说明或返回值说明时由断言报告具体位置。
    """
    problems: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstring = ast.get_docstring(node, clean=False) or ""
            location = f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} {node.name}"
            if not any("\u4e00" <= char <= "\u9fff" for char in docstring):
                problems.append(f"{location} 缺少中文 Docstring")
            for argument in _function_arguments(node):
                if f":param {argument}:" not in docstring:
                    problems.append(f"{location} 缺少 :param {argument}:")
            if ":return:" not in docstring:
                problems.append(f"{location} 缺少 :return:")

    assert not problems, "\n" + "\n".join(problems)
