import time
from typing import Optional

class Timer:
    def __init__(self, verbose: bool = True):
        """
        verbose=True: start/end 时打印提示；False: 静默
        """
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.note: str = ""
        self.verbose: bool = verbose

    def set_verbose(self, verbose: bool) -> None:
        """动态切换是否打印"""
        self.verbose = verbose

    def start(self, note: str = "", verbose: Optional[bool] = None):
        """
        开始计时；可传入 verbose 临时覆盖是否打印
        """
        eff_verbose = self.verbose if verbose is None else verbose
        self.start_time = time.time()
        self.end_time = None
        self.note = note
        if eff_verbose:
            print(f"计时开始...（备注：{note}）" if note else "计时开始...")

    def end(self, verbose: Optional[bool] = None) -> float:
        """
        结束计时并返回耗时（秒）；可传入 verbose 临时覆盖是否打印
        """
        if self.start_time is None:
            raise ValueError("请先调用 start() 再调用 end()")
        eff_verbose = self.verbose if verbose is None else verbose
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        if eff_verbose:
            if self.note:
                print(f"计时结束（备注：{self.note}），用时 {duration:.4f} 秒")
            else:
                print(f"计时结束，用时 {duration:.4f} 秒")
        return duration

    def elapsed(self) -> float:
        """返回当前已用时（秒）；若未结束则以当前时间计算"""
        if self.start_time is None:
            return 0.0
        end = self.end_time if self.end_time is not None else time.time()
        return end - self.start_time