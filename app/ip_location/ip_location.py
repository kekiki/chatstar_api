import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

from qqwry import QQwry

class IPLocationResult:
    def __init__(self, ip, addr, isp):
        self.ip = ip
        self.addr = addr
        self.isp = isp
        self.country = addr.split('–')[0] if addr else None

class IPLocation:
    def __init__(self):
        self.q = QQwry()
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
    result = ip_location.get_ip_location('171.83.48.236')
    print(result.addr, result.isp)