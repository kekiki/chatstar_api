import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

from qqwry import QQwry

class IPLocationResult:
    def __init__(self, ip, country, isp):
        self.ip = ip
        self.country = country
        self.isp = isp
        self.country = country.split('–')[0] if country else ''

class IPLocation:
    def __init__(self):
        self.q = QQwry()
        #  更新地址
        # https://github.com/metowolf/qqwry.dat/releases/latest/download/qqwry.dat
        dat_path = os.path.join(os.path.dirname(__file__), "qqwry.dat")
        self.q.load_file(dat_path)

    def get_ip_location(self, ip):
        result = self.q.lookup(ip)
        if result is None:
            return None
        addr, isp = result
        return IPLocationResult(ip, addr, isp)

ip_location = IPLocation()

if __name__ == '__main__':
    result = ip_location.get_ip_location('117.96.40.33')
    print(result.country, result.isp)

# import os
# import ipaddress
# from czdb.db_searcher import DbSearcher

# class IPLocationResult:
#     def __init__(self, ip: str, country: str = '', province: str = '', city: str = '', isp: str = ''):
#         self.ip = ip
#         self.country = country
#         self.province = province
#         self.city = city
#         self.isp = isp

# class IPLocation:
#     """
#     授权有效期至2027年07月09日。
#     IP地址查询李现数据库CZDB更新地址:
#     https://www.cz88.net/api/communityIpAuthorization/communityIpDbFile?fn=czdb&key=d5c09f8a-a976-38cb-b5bb-4cb74bc37f22

#     批量查询：对于批量查询，建议使用 "MEMORY" 模式。这是因为 "MEMORY" 模式会将数据库加载到内存中，从而提高查询速度，尤其是在处理大量查询时。虽然这会增加内存的使用，但可以显著提高批量处理的效率。
#     少量查询：如果每个请求只查询少量的 IP 地址，那么使用 "BTREE" 模式可能更合适。"BTREE" 模式不需要预先加载整个数据库到内存中，适用于处理较少量的查询请求，可以减少内存的使用，同时保持良好的查询性能。
#     """
#     def __init__(self):
#         v4_path = os.path.join(os.path.dirname(__file__), "cz88_public_v4.czdb")
#         v6_path = os.path.join(os.path.dirname(__file__), "cz88_public_v6.czdb")
#         key = "X4r41fgcFMO5TiKPz+AmUA=="
#         self.query_type = "BTREE" 
#         self.searcher_v4 = DbSearcher(v4_path, self.query_type, key)
#         self.searcher_v6 = DbSearcher(v6_path, self.query_type, key)

#     def _parse_region(self, ip: str, region_str: str) -> dict:
#         """
#         拆分纯真返回的地址字符串
#         格式示例：中国|广东省|深圳市|电信   
#         返回：{country, province, city, isp}
#         """
#         parts = region_str.split("|")
#         # 补齐四段，不足填空字符串
#         while len(parts) < 4:
#             parts.append("")
#         country, province, city, isp = parts[:4]
#         return IPLocationResult(ip, country.strip(), province.strip(), city.strip(), isp.strip())

#     def get_ip_location(self, ip):
#         """
#         对外统一查询入口
#         :param ip: IP字符串（IPv4/IPv6）
#         :return: IPLocationResult
#         """
#         try:
#             ip_obj = ipaddress.ip_address(ip)
#         except ValueError:
#             return IPLocationResult(ip, "未知", "", "", "无效IP地址")

#         try:
#             if isinstance(ip_obj, ipaddress.IPv4Address):
#                 searcher = self.searcher_v4
#             else:
#                 searcher = self.searcher_v6

#             region = searcher.search(ip)
#             print("搜索结果：")
#             print(region)

#             return self._parse_region(ip, region)

#         except Exception as e:
#             return IPLocationResult(ip, "未知", "", "", f"查询失败: {str(e)}")
        
#     def close(self):
#         """程序退出时手动关闭所有数据库文件"""
#         self.searcher_v4.close()
#         self.searcher_v6.close()

# ip_location = IPLocation()

# if __name__ == "__main__":
#     res = ip_location.get_ip_location("66.249.66.193")
#     print(f"[{res.ip}]-[{res.country}]-[{res.province}]-[{res.city}]-[{res.isp}]")
#     ip_location.close()