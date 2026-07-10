class UserAgent(object):
    """
    User agent object
    """
    def __init__(self, user_agent: str):
        infos = user_agent.split(',')
        # 补齐六段，不足填空字符串
        while len(infos) < 6:
            infos.append("")
        self.app_name, self.app_version, self.build_number, self.deviceModel, self.osVersion, self.brand, self.manufacturer = infos[:6]
