# Author: Acer Zhang
# Datetime: 2021/5/26 
# Copyright belongs to the author.
# Please indicate the source for reprinting.
import os
from collections import OrderedDict

from qpt.kernel.qos import dynamic_load_package, get_qpt_tmp_path, ArgManager
from qpt.kernel.qlog import clean_stout, Logging
from qpt.kernel.qterminal import PTerminal, TerminalCallback, LoggingTerminalCallback
from qpt.kernel.qcode import PythonPackages

TSINGHUA_PIP_SOURCE = "https://pypi.tuna.tsinghua.edu.cn/simple"
BAIDU_PIP_SOURCE = "https://mirror.baidu.com/pypi/simple"
DOUBAN_PIP_SOURCE = "https://pypi.douban.com/simple"
BFSU_PIP_SOURCE = "https://mirrors.bfsu.edu.cn/pypi/web/simple"
PYPI_PIP_SOURCE = "https://pypi.python.org/simple"
DEFAULT_PIP_SOURCE = BFSU_PIP_SOURCE

SIGNALS = ["=", "~", "<", ">"]

QPT_DISPLAY_FLAG = "#$QPT_FLAG$"
DISPLAY_IGNORE = "ignore"
DISPLAY_COPY = "copy"
DISPLAY_FORCE = "force"  # 独立安装
DISPLAY_NET_INSTALL = "net_install"  # 打包时从第三方站点下载，部署时安装
DISPLAY_ONLINE_INSTALL = "online_install"  # 在线安装
DISPLAY_LOCAL_INSTALL = "local_install"  # 本地下载后安装
DISPLAY_SETUP_INSTALL = "setup_install"  # 直接安装


class DisplayFlag(dict):
    def __init__(self):
        super(DisplayFlag, self).__init__({"ignore": DISPLAY_IGNORE,
                                           "copy": DISPLAY_COPY,
                                           "force": DISPLAY_FORCE,
                                           "net_install": DISPLAY_NET_INSTALL,
                                           "local_install": DISPLAY_LOCAL_INSTALL,
                                           "online_install": "online_install",
                                           None: None})

    def get_flag(self, item):
        if item is None:
            return None
        if DISPLAY_NET_INSTALL in item:
            return item
        else:
            for flag in self.keys():
                if flag in item:
                    return flag
            return None


display_flag = DisplayFlag()


class PIPTerminal(PTerminal):
    # ToDo 此处需要简化
    def __init__(self, python_path):
        super(PIPTerminal, self).__init__()
        self.head = os.path.abspath(python_path) + " -m pip"

    def shell_func(self, callback: TerminalCallback = LoggingTerminalCallback()):
        def closure(closure_shell):
            if isinstance(closure_shell, list):
                tmp = [" " + bit_shell for bit_shell in closure_shell]
                closure_shell = "".join(tmp)
            closure_shell = self.head + closure_shell
            if closure_shell[1:3] == ":\\":
                closure_shell = f"cd {closure_shell[:2]} ;" + closure_shell
            Logging.debug(f"SHELL: {closure_shell}")
            closure_shell = f'{closure_shell}; echo "---QPT OUTPUT STATUS CODE---" ;$? \n'
            # 发送指令
            try:
                final_shell = closure_shell.encode("utf-8")
            except Exception as e:
                Logging.error("执行该指令时遇到解码问题，目前将采用兼容模式进行，原始报错如下：\n" + str(e))
                final_shell = closure_shell.encode("utf-8", errors="ignore")
            self.main_terminal.stdin.write(final_shell)
            try:
                self.main_terminal.stdin.flush()
            except Exception as e:
                Logging.error(str(e))

            # 捕获PIP的异常
            callback.error_fitter = ["ERROR:"]
            callback.normal_fitter = ["requires click, which is not installed.\nqpt",
                                      "ERROR: pip's dependency resolver "]
            callback.handle(self.main_terminal)

        return closure


def analysis_requirement_line(name: str):
    name = name.strip("\n")

    display = None
    if QPT_DISPLAY_FLAG in name:
        name, display = name.split(QPT_DISPLAY_FLAG)

    version = ""

    for _signal in SIGNALS:
        if _signal in name:
            version = name[name.index(_signal):]
            name = name[:name.index(_signal)]
            break
    return name, version, display


class PipTools:
    """
    Python解释器管理器
    """

    def __init__(self,
                 source: str = None,
                 pip_path=None):
        if source is None:
            source = DEFAULT_PIP_SOURCE
        if pip_path:
            pip_main = dynamic_load_package(packages_name="pip", lib_packages_path=pip_path).main
        else:
            from pip._internal.cli.main import main as pip_main
        self.pip_main = pip_main
        self.source = source

        # 安静模式
        self.quiet = True if os.getenv("QPT_MODE") == "Run" else False
        if self.quiet:
            Logging.debug("PipTools进入安静模式")

        # ToDo 可考虑增加环境管理部分 - 可考虑生成软链
        pass

    def pip_shell(self, shell: str):
        if not os.path.exists(get_qpt_tmp_path('pip_cache')):
            os.makedirs(get_qpt_tmp_path('pip_cache'), exist_ok=True)
        shell += f" --isolated --disable-pip-version-check --cache-dir {get_qpt_tmp_path('pip_cache')}" \
                 f" --timeout 10 --prefer-binary"
        if self.quiet:
            shell += " --quiet"
        self.pip_main(str(shell).split(" "))
        clean_stout(['console', 'console_errors', 'console_subprocess'])

    def pip_package_shell(self,
                          package: str = None,
                          version: str = None,
                          act="install",
                          no_dependent=False,
                          find_links: str = None,
                          opts: ArgManager = None):
        if opts is None:
            opts = ArgManager()
        else:
            if not isinstance(opts, ArgManager):
                Logging.warning(f"在键入以下指令时，opts传递的并非是ArgManager对象，可能存在意料之外的问题\n{opts}")

        #  package兼容性
        package = package.replace("-", "_")

        if version:
            for signal in SIGNALS:
                if signal in version:
                    package += version
                    break
            else:
                package += "==" + version

        opts = ArgManager([act, package]) + opts

        if no_dependent:
            opts += "--no-deps"

        if find_links:
            opts += "-f " + find_links
        else:
            opts += ["-i", self.source]

        self.pip_shell(str(opts))

    def download_package(self,
                         package: str,
                         save_path: str,
                         version: str = None,
                         no_dependent=False,
                         find_links: str = None,
                         python_version: str = None,
                         opts: ArgManager = None):
        if opts is None:
            opts = ArgManager()

        opts += "-d " + save_path
        if python_version:
            opts += "--python-version " + python_version
            opts += "--only-binary :all:"

        # pip download xxx -d ./test
        # pip install xxx -f ./test --no-deps
        self.pip_package_shell(package=package,
                               version=version,
                               act="download",
                               no_dependent=no_dependent,
                               find_links=find_links,
                               opts=opts)

    def install_local_package(self,
                              package: str,
                              abs_package: bool = False,  # abs则不会替换下划线，通常用于绝对路径whl安装
                              version: str = None,
                              whl_dir: str = None,
                              no_dependent=False,
                              opts: ArgManager = None):
        if opts is None:
            opts = ArgManager()

        opts += "--no-index"

        if abs_package:
            act = "install " + package
            package = ""
        else:
            act = "install"
        self.pip_package_shell(package=package,
                               act=act,
                               version=version,
                               no_dependent=no_dependent,
                               find_links=whl_dir,
                               opts=opts)

    def analyze_dependence(self,
                           analyze_path,
                           save_file_path=None,
                           return_path=False,
                           action_mode=False):  # action mode为静默模式

        if save_file_path is None:
            save_file_path = os.path.join(analyze_path, "requirements_with_opt.txt")

        requires, dep, ignore_requires = PythonPackages.intelligent_analysis(analyze_path, return_all_info=True)

        with open(save_file_path, "w", encoding="utf-8") as req_file:
            req_file.write("# Here is the list of packages automatically derived by QPT\n"
                           "# you can ignore the dependent packages in the main package and only care "
                           "about the main package\n"
                           "# For example, you need to install paddlepaddle and pillow, because paddlepaddle "
                           "relies on pillow, so you only need to install paddlepaddle.\n"
                           "# ---------------------------------------------------------------------\n"
                           "# QPT Home:        https://github.com/GT-ZhangAcer/QPT\n"
                           "# ---------------------------------------------------------------------\n"
                           "# \n"
                           "# -------------Mainly depends on package analysis results--------------\n\n")
            temp_write = "\n# ----------------------Ignored sub dependent packages---------------------\n"
            for require_name, require_version in requires.items():
                req_file.write(f"{require_name}=={require_version}\n")
                if dep[require_name]:
                    temp_write += f"\n# -----Dependencies of {require_name}\n"
                    for dep_name, dep_version in dep[require_name].items():
                        if not dep_version:
                            dep_version = ""
                        temp_write += f"#{dep_name}{dep_version}\n"

            req_file.write("\n# ----------------------Ignored dependent packages---------------------\n")
            for ignore_require_name, ignore_require_version in ignore_requires.items():
                req_file.write(f"#{ignore_require_name}=={ignore_require_version}\n")
            req_file.write(temp_write)

        Logging.info(f"依赖分析完毕!\n"
                     f"已在\033[32m{os.path.abspath(save_file_path)}\033[0m 中创建了依赖列表\n"
                     f"Tips 1: 查看文件后可能需要关闭查看该文件的文本查看器，这样可以有效避免文件被占用\n"
                     f"Tips 2: 请务必检查上方文件中所写入的依赖列表情况，因为自动分析并不能保证程序依赖均可以被检出\n"
                     f"        若在执行EXE时提示:ImportError: No module named xxx 报错信息，请在该依赖文件中加入xxx或取消xxx前的 # 符号\n"
                     f"---------------------------------------------------------------------\n"
                     f"\033[41m请在检查/修改依赖文件后\033[0m在此处按下回车键继续...\n"
                     f"请键入指令[回车键 - 一次不行可以试试按两次]:_", line_feed=False)

        if not action_mode:
            input()
        if return_path:
            return save_file_path
        else:
            return self.analyze_requirements_file(save_file_path)

    @staticmethod
    def analyze_requirements_file(file_path):
        requirements = dict()
        try:
            with open(file_path, "r", encoding="utf-8") as req_file:
                data = req_file.readlines()
                for line in data:
                    if "#" == line[0]:
                        continue
                    package, version, display = analysis_requirement_line(line)
                    requirements[package] = {"version": version,
                                             "display": display_flag.get_flag(display),
                                             "QPT_Flag": True if display else False}
        except Exception as e:
            raise Exception(f"{file_path}文件解析失败，文件可能被其他程序占用或格式异常\n"
                            f"报错信息如下：{e}")
        return requirements

    @staticmethod
    def save_requirements_file(requirements: dict, save_file_path, encoding="utf-8"):
        with open(save_file_path, "w", encoding=encoding) as file:
            for requirement, requirement_info in requirements.items():
                version = requirement_info.get("version", "")
                display = requirement_info.get("display", "")
                qpt_flag = requirement_info.get("QPT_Flag", False)
                if version is None or version == "":
                    version = ""
                else:
                    for _signal in SIGNALS:
                        if _signal in version:
                            break
                    else:
                        version = "==" + version
                if qpt_flag and display:
                    line = f"{requirement}{version} {QPT_DISPLAY_FLAG}{display}\n"
                else:
                    line = f"{requirement}{version}\n"
                file.write(line)

    @staticmethod
    def flatten_requirements(requirements: dict):
        """
        打平依赖情况
        :param: {package: version_sig} # {QPT: ==1.0b1.dev1}
        :return: requirements: {package: abs_version} # {QPT: 1.0b1.dev1}
        """
        all_req = OrderedDict()
        packages_dist, _, dep_pkg_dict = PythonPackages.search_packages_dist_info()

        def get_next_dep(dep_name: str, version=None):
            if dep_name not in all_req:
                all_req[dep_name] = packages_dist.get(dep_name) if version is None else version

                sub_deps = dep_pkg_dict.get(dep_name.lower())
                if sub_deps:
                    for sub_dep in sub_deps:
                        if sub_dep not in all_req:
                            get_next_dep(dep_name=sub_dep, version=packages_dist.get(sub_dep))

        for requirement in requirements:
            get_next_dep(dep_name=requirement, version=requirements[requirement])
        return all_req


if __name__ == '__main__':
    pass
