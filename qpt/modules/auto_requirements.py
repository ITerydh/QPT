# Author: Acer Zhang
# Datetime:2021/7/3 
# Copyright belongs to the author.
# Please indicate the source for reprinting.
import os

from qpt.kernel.qlog import Logging
from qpt.kernel.qos import get_qpt_tmp_path, ArgManager, download
from qpt.kernel.qinterpreter import display_flag, DISPLAY_IGNORE, DISPLAY_COPY, DISPLAY_FORCE, DISPLAY_NET_INSTALL, \
    DISPLAY_LOCAL_INSTALL, DISPLAY_SETUP_INSTALL, DISPLAY_ONLINE_INSTALL
from qpt.modules.package import _RequirementsPackage, DEFAULT_DEPLOY_MODE, CustomPackage, CopyWhl2Packages
from qpt.modules.paddle_family import PaddlePaddlePackage, PaddleOCRPackage
from qpt.memory import QPT_MEMORY


class AutoRequirementsPackage(_RequirementsPackage):
    """
    注意，这并不是个普通的Module
    """

    def __init__(self,
                 path,
                 deploy_mode=DEFAULT_DEPLOY_MODE):
        """
        自动获取Requirements
        :param path: 待扫描的文件夹路径或requirements文件路径，若提供了requirements文件路径则不会自动分析依赖情况
        :param deploy_mode: 部署模式
        """
        if not os.path.exists(path):
            Logging.info(f"当前路径{os.path.abspath(path)}中不存在Requirements文件，"
                         f"请优先检查路径是否提供正确，必要时使用绝对路径")

        if os.path.isfile(path):
            Logging.info(f"正在读取{os.path.abspath(path)}下的依赖情况...")
            requirements = QPT_MEMORY.pip_tool.analyze_requirements_file(path)
        else:
            Logging.info(f"[Auto]正在分析{os.path.abspath(path)}下的依赖情况...")
            requirements = QPT_MEMORY.pip_tool.analyze_dependence(path,
                                                                  return_path=False,
                                                                  action_mode=QPT_MEMORY.action_flag)

        flatten_requirements = QPT_MEMORY.pip_tool.flatten_requirements(dict([(_r, requirements[_r].get("version"))
                                                                              for _r in requirements]))
        flatten_requirements_fix = dict([(_r, {"version": flatten_requirements.get(_r),
                                               "display": deploy_mode,
                                               "QPT_Flag": False})
                                         for _r in flatten_requirements])
        flatten_requirements_fix.update(requirements)
        pre_add_module = list()
        for requirement in dict(flatten_requirements_fix):
            requirement, version, display, qpt_flag = requirement, \
                                                      flatten_requirements_fix[requirement].get("version"), \
                                                      flatten_requirements_fix[requirement].get("display"), \
                                                      flatten_requirements_fix[requirement].get("QPT_Flag")
            # 对特殊包进行过滤和特殊化
            if requirement in SPECIAL_MODULE:
                special_module, parameter = SPECIAL_MODULE[requirement]
                parameter["version"] = version
                parameter["deploy_mode"] = deploy_mode if not display else display
                module = special_module(**parameter)
                pre_add_module.append(module)
                flatten_requirements_fix.pop(requirement)
            # 使用依赖文件中指定的方式封装
            elif qpt_flag and display:
                sub_display_mode = display_flag.get_flag(display)
                if sub_display_mode == DISPLAY_IGNORE:
                    flatten_requirements_fix.pop(requirement)
                elif sub_display_mode == DISPLAY_FORCE:
                    pre_add_module.append(CustomPackage(package=requirement,
                                                        version=version,
                                                        deploy_mode=deploy_mode,
                                                        no_dependent=True,
                                                        name=f"{sub_display_mode}_" + requirement))
                    flatten_requirements_fix.pop(requirement)
                elif sub_display_mode == DISPLAY_NET_INSTALL:
                    # 从指定链接处下载whl文件
                    _, whl_path = download(
                        url=f"{sub_display_mode[len(DISPLAY_NET_INSTALL) + 1:]}",
                        file_name=None)
                    pre_add_module.append(CopyWhl2Packages(whl_path=whl_path))
                    flatten_requirements_fix.pop(requirement)
                elif sub_display_mode in [DISPLAY_LOCAL_INSTALL,
                                          DISPLAY_SETUP_INSTALL,
                                          DISPLAY_ONLINE_INSTALL,
                                          DISPLAY_COPY]:
                    pre_add_module.append(CustomPackage(package=requirement,
                                                        version=version,
                                                        deploy_mode=sub_display_mode,
                                                        no_dependent=True,
                                                        name=f"{sub_display_mode}_" + requirement))
                    flatten_requirements_fix.pop(requirement)
                else:
                    raise IndexError(f"当前特殊指令{display}无法识别，"
                                     f"请在requirement.txt中修改对{requirement}依赖的#$QPT_FLAG$ copy特殊操作指令")

        # 保存依赖至
        requirements_path = os.path.join(get_qpt_tmp_path(), "requirements_dev.txt")
        QPT_MEMORY.pip_tool.save_requirements_file(flatten_requirements_fix, requirements_path)

        # 执行常规的安装
        super().__init__(requirements_file_path=requirements_path,
                         deploy_mode=deploy_mode)
        for pam in pre_add_module:
            self.add_ext_module(pam)


# 自动推理依赖时需要特殊处理的Module配置列表 格式{包名: (Module, Module参数字典)}
# version、deploy_mode 为必填字段
# ToDo 小心 DEFAULT_DEPLOY_MODE 不在mem中可能会有问题
SPECIAL_MODULE = {"paddlepaddle": (PaddlePaddlePackage, {"version": None,
                                                         "include_cuda": False,
                                                         "deploy_mode": DEFAULT_DEPLOY_MODE}),
                  "paddlepaddle-gpu": (PaddlePaddlePackage, {"version": None,
                                                             "include_cuda": True,
                                                             "deploy_mode": DEFAULT_DEPLOY_MODE}),
                  "paddleocr": (PaddleOCRPackage, {"version": None,
                                                   "deploy_mode": DEFAULT_DEPLOY_MODE})}
