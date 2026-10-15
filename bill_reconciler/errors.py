"""退出码常量与领域异常。

退出码契约（plan/02 §4.5）：

===== ==========================================================
码    语义
===== ==========================================================
0     完成且无未决事项
1     完成但检出需人工处理的问题（清单必打印，不静默）
2     用法或输入不可用（未知命令 / 缺参 / 文件形态不可用）
3     环境不可用（数据目录解析失败、可选依赖缺失）
===== ==========================================================

领域异常一律继承 ``BillReconcilerError(ValueError)``：
CLI 只捕获该基类并映射退出码，保证"该报的错"不会逃逸成裸 traceback，
也保证真实内部缺陷不被 ``except Exception`` 吞掉。
"""

EXIT_OK = 0
EXIT_ISSUES = 1
EXIT_USAGE = 2
EXIT_ENV = 3


class BillReconcilerError(ValueError):
    """领域异常基类；子类固定 exit_code，CLI 据此映射退出码。"""

    exit_code = EXIT_USAGE


class UsageError(BillReconcilerError):
    """用法错误（缺参、参数非法等）。"""

    exit_code = EXIT_USAGE


class InputError(BillReconcilerError):
    """输入不可用（文件不存在、整份文件形态失败等）。"""

    exit_code = EXIT_USAGE


class EnvError(BillReconcilerError):
    """环境不可用（数据目录解析失败、可选依赖缺失等）。"""

    exit_code = EXIT_ENV


class NotImplementedYet(BillReconcilerError):
    """骨架期占位命令：功能尚未实现（随对应里程碑移除）。

    临时按退出码 2（"当前不可用"）处理；命令真正实现后，
    测试期望按 plan/02 §4.5 的最终语义翻转。
    """

    exit_code = EXIT_USAGE

    def __init__(self, command, milestone):
        message = "命令 %s 尚未实现（计划于 %s 提供，见 plan/05-里程碑.md）" % (command, milestone)
        super().__init__(message)
        self.command = command
        self.milestone = milestone
