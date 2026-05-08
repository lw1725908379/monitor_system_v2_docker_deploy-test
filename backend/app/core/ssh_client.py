import paramiko
import re
import json
from datetime import datetime
from backend.app.utils.logger import logger
from backend.app.core.config import Config


class SSHClient:
    def __init__(self, ip, username, password):
        self.ip = ip
        self.username = username
        self.password = password
        self.client = None
        self.cmds = Config.LINUX_COMMANDS

    def connect(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                self.ip,
                username=self.username,
                password=self.password,
                timeout=Config.SSH_CONFIG['connect_timeout']
            )
            return True
        except Exception as e:
            logger.error(f"[{self.ip}] SSH连接失败: {e}")
            return False

    def close(self):
        if self.client:
            self.client.close()

    def execute_cmd(self, cmd):
        if not self.client:
            return ""
        try:
            stdin, stdout, stderr = self.client.exec_command(
                cmd,
                timeout=Config.SSH_CONFIG['exec_timeout']  # 从配置获取超时
            )
            return stdout.read().decode('utf-8', errors='ignore').strip()
        except Exception as e:
            logger.error(f"[{self.ip}] 命令执行失败: {cmd}, 错误: {e}")
            return ""

    def get_cpu_usage(self):
        """获取CPU使用率 (自开机以来的平均值)"""
        try:
            output = self.execute_cmd(self.cmds['CPU_STAT'])
            if output:
                parts = output.split()
                # /proc/stat 格式: cpu  user nice system idle ...
                total = sum(map(int, parts[1:]))
                idle = int(parts[4])
                if total > 0:
                    usage = 100 * (1 - idle / total)
                    return round(usage, 2)
            return 0.0
        except Exception:
            return 0.0

    # def check_memory(self, threshold=80):
    #     """检查内存和高占用进程"""
    #     result = {'usage': 0.0, 'high_processes': []}
    #     try:
    #         out_free = self.execute_cmd(self.cmds['MEM_FREE'])
    #         total_mem_kb = 1  # 默认值防止除零
    #
    #         if out_free:
    #             parts = out_free.split()
    #             if len(parts) >= 2:
    #                 total = int(parts[0])
    #                 used = int(parts[1])
    #                 if total > 0:
    #                     result['usage'] = round((used / total) * 100, 2)
    #                     total_mem_kb = total
    #
    #         out_ps = self.execute_cmd(self.cmds['TOP_PROCESSES'])
    #         if out_ps:
    #             lines = out_ps.split('\n')[1:]
    #             min_pct = Config.MONITOR_CONFIG.get('process_mem_min_pct', 1.0)  # 获取配置阈值
    #
    #             for line in lines:
    #                 parts = line.split()
    #                 if len(parts) >= 4:
    #                     pid, user, comm, rss = parts[0], parts[1], parts[2], parts[3]
    #                     mem_pct = (int(rss) / total_mem_kb) * 100
    #
    #                     # 过滤掉占用极低的进程
    #                     if mem_pct > min_pct:
    #                         result['high_processes'].append({
    #                             'pid': pid, 'command': comm, 'rss_kb': rss,
    #                             'mem_percent': round(mem_pct, 2)
    #                         })
    #
    #         # TODO:过滤超过总阈值 1/10 的大进程 (保留原有逻辑)
    #         # 例如内存阈值80%，则只显示超过8%的进程
    #         filter_limit = threshold / 10
    #         result['high_processes'] = [p for p in result['high_processes']
    #                                     if p['mem_percent'] > filter_limit]
    #
    #         return result
    #     except Exception as e:
    #         logger.error(f"[{self.ip}] 内存检查失败: {e}")
    #         return result

    def check_memory(self, threshold=80):
        """检查内存和高占用进程"""
        result = {'usage': 0.0, 'high_processes': []}
        try:
            out_free = self.execute_cmd(self.cmds['MEM_FREE'])
            total_mem_kb = 1
            if out_free:
                parts = out_free.split()
                if len(parts) >= 2:
                    total = int(parts[0])
                    used = int(parts[1])
                    if total > 0:
                        result['usage'] = round((used / total) * 100, 2)
                        total_mem_kb = total

            # 获取配置的数量，默认为 5
            top_count = Config.MONITOR_CONFIG.get('top_process_count', 5)
            # 构造命令：因为 ps 有标题行，所以 head 要取 count + 1
            cmd_ps = self.cmds['TOP_PROCESSES'].format(count=top_count + 1)

            out_ps = self.execute_cmd(cmd_ps)
            if out_ps:
                lines = out_ps.split('\n')[1:]
                min_pct = Config.MONITOR_CONFIG.get('process_mem_min_pct', 1.0)

                for line in lines:
                    parts = line.split()
                    if len(parts) >= 4:
                        pid, user, comm, rss = parts[0], parts[1], parts[2], parts[3]
                        try:
                            rss_val = int(rss)
                        except ValueError:
                            continue

                        mem_pct = (rss_val / total_mem_kb) * 100

                        if mem_pct > min_pct:
                            result['high_processes'].append({
                                'pid': pid,
                                'command': comm,  # 进程名
                                'rss_kb': rss_val,
                                'mem_percent': round(mem_pct, 2)
                            })

            return result
        except Exception as e:
            logger.error(f"[{self.ip}] 内存检查失败: {e}")
            return result

    def check_core_files(self, path):
        """检查 Core 文件"""
        result = []
        cmd = self.cmds['FIND_CORE_FILES'].format(path=path)
        output = self.execute_cmd(cmd)

        if not output: return []

        for line in output.split('\n'):
            line = line.strip()
            if line and 'core-' in line:
                result.append({'filename': line, 'size': '0', 'timestamp': ''})
        return result

    def check_risk_processes(self, risk_list):
        """检查风险进程 (适配 BusyBox)"""
        results = []
        for risk in risk_list:
            process_name = risk['process_name']
            limit_mb = risk['allocated_memory']

            risk['current_memory'] = 0
            risk['alert_triggered'] = False
            risk['fetched_pid'] = None

            try:
                cmd_pidof = self.cmds['PIDOF'].format(process_name=process_name)
                pid_output = self.execute_cmd(cmd_pidof)

                if not pid_output:
                    cmd_grep = self.cmds['PS_GREP'].format(process_name=process_name)
                    pid_output = self.execute_cmd(cmd_grep)

                if pid_output and pid_output.strip():
                    current_pid = pid_output.strip().split()[0]
                    risk['fetched_pid'] = current_pid

                    cmd_mem = self.cmds['PROC_STATUS_VMRSS'].format(pid=current_pid)
                    mem_output = self.execute_cmd(cmd_mem)

                    if mem_output and "kB" in mem_output:
                        numbers = re.findall(r'\d+', mem_output)
                        if numbers:
                            rss_kb = int(numbers[0])
                            rss_mb = rss_kb / 1024
                            risk['current_memory'] = round(rss_mb, 2)

                            # 仅对手动配置的进程检查内存超限（allocated_memory > 0）
                            if risk.get('source') == 'manual' and limit_mb > 0 and rss_mb > limit_mb:
                                risk['alert_triggered'] = True
                                risk['alert_msg'] = f"内存超限: {risk['current_memory']}MB > {limit_mb}MB"

                # 总是返回结果，用于检测PID变化
                results.append(risk)

            except Exception as e:
                logger.error(f"[{self.ip}] 检查进程 {process_name} 失败: {e}")

        return results

    def get_device_details(self):
        """获取设备详细信息"""
        baseinfo = {}
        project_info = {}

        try:
            # 1. 读取 baseinfo.json
            base_output = self.execute_cmd(self.cmds["BASEINFO_CMD"])
            if base_output:
                try:
                    data = json.loads(base_output)
                    for key in ["cpuId", "devId", "deviceId", "mac", "project_number"]:
                        if key in data: baseinfo[key] = data[key]
                except Exception:
                    pass

            # 2. 读取 project_info.json
            proj_output = self.execute_cmd(self.cmds["PROJECT_CMD"])
            if proj_output:
                try:
                    p_data = json.loads(proj_output)
                    if "project_number" in p_data:
                        project_info["project_number"] = p_data["project_number"]
                except Exception:
                    pass

            return baseinfo, project_info
        except Exception as e:
            logger.error(f"[{self.ip}] 获取设备详情异常: {e}")
            return {}, {}

    def get_thermal_zones(self):
        """获取热区温度"""
        result = []
        try:
            output = self.execute_cmd(self.cmds['THERMAL_ZONES'])
            if output:
                for line in output.split('\n'):
                    if ':' in line:
                        parts = line.strip().split(':')
                        if len(parts) == 2:
                            try:
                                temp = float(parts[1])
                                result.append({
                                    'zone': parts[0],
                                    'temp': temp
                                })
                            except ValueError:
                                pass
            return result
        except Exception as e:
            logger.error(f"[{self.ip}] 获取热区温度异常: {e}")
            return []

    def get_network_stats(self, interface='eth0'):
        """获取网络流量统计"""
        try:
            result = {
                'interface': interface,
                'rx_bytes': 0,
                'tx_bytes': 0,
                'rx_rate': 0,
                'tx_rate': 0,
                'bandwidth_mbps': 100,
                'latency_ms': 0,
                'packet_loss': 0
            }

            # 获取网络接口流量 /proc/net/dev
            output = self.execute_cmd(f"cat /proc/net/dev | grep {interface}")
            if output:
                parts = output.split()
                if len(parts) >= 11:
                    result['rx_bytes'] = int(parts[1])
                    result['tx_bytes'] = int(parts[9])

            # 获取网卡带宽 (尝试从 ethtool 获取)
            eth_output = self.execute_cmd(f"ethtool {interface} 2>/dev/null | grep Speed")
            if eth_output and 'Speed:' in eth_output:
                try:
                    speed_str = eth_output.split(':')[1].strip().replace('Mb/s', '')
                    result['bandwidth_mbps'] = int(speed_str)
                except:
                    pass

            # 测试网络延迟和丢包 (ping 本地网关或常用地址)
            ping_output = self.execute_cmd("ping -c 3 -W 2 8.8.8.8 2>/dev/null | tail -1")
            if ping_output:
                # 解析: 3 packets transmitted, 3 received, 0% packet loss, time 2003ms
                if 'packet loss' in ping_output:
                    try:
                        loss_str = ping_output.split(',')[2].split('%')[0].strip()
                        result['packet_loss'] = float(loss_str)
                    except:
                        pass
                # 解析: rtt min/avg/max/mdev = 1.234/2.345/3.456/0.123 ms
                if 'rtt min' in ping_output or 'avg' in ping_output:
                    try:
                        avg_str = ping_output.split('/')[4] if '/' in ping_output else '0'
                        result['latency_ms'] = float(avg_str.replace(' ms', ''))
                    except:
                        pass

            return result
        except Exception as e:
            logger.error(f"[{self.ip}] 获取网络统计异常: {e}")
            return None