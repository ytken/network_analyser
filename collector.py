import requests
import json
import time
import paramiko
import glob, os

class NetworkCollector:
    def __init__(self, netbox_url, netbox_token, ssh_key=None, ssh_password=None):
        self.netbox_url = netbox_url.rstrip('/')
        self.netbox_token = netbox_token
        self.ssh_key = ssh_key
        self.ssh_password = ssh_password

        files = glob.glob('json_data/*')
        for f in files:
            os.remove(f)

    def get_devices_from_netbox(self):
        headers = {
            'Authorization': f'Token {self.netbox_token}',
            'Content-Type': 'application/json',
        }
        url = f'{self.netbox_url}/api/dcim/devices/?role=server_container_host'
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to get devices from NetBox: {response.status_code} {response.text}")
        data = response.json()
        return data.get('results', [])

    def ssh_connect(self, host, username, password=None, key_filename=None):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=username, password=password, key_filename=key_filename)
        return client

    def get_host_network_snapshot(self, ssh_client):
        commands = {
            'hostname': 'hostname',
            'interfaces': 'ip a',
            'routes': 'ip r',
            'sockets': 'ss -tulpen',
            'iptables': 'sudo iptables -L -n -v',
        }
        snapshot = {}
        for key, cmd in commands.items():
            stdin, stdout, stderr = ssh_client.exec_command(cmd)
            output = stdout.read().decode('utf-8').strip()
            error = stderr.read().decode('utf-8').strip()
            snapshot[key] = output if output else error
        return snapshot

    def get_docker_network_info(self, ssh_client):
        docker_info = {}
        stdin, stdout, stderr = ssh_client.exec_command("docker ps -q")
        container_ids = stdout.read().decode('utf-8').strip().splitlines()
        for cid in container_ids:
            if cid:
                cmd = f"docker inspect {cid}"
                stdin, stdout, stderr = ssh_client.exec_command(cmd)
                out_json = stdout.read().decode('utf-8').strip()
                try:
                    info = json.loads(out_json)
                except Exception:
                    info = out_json
                docker_info[cid] = info
        return docker_info

    def get_docker_events(self, ssh_client):
        now = int(time.time())
        since = now - 300
        cmd = "docker events --since 300s --until \"$(date +%s)\" --format '{{json .}}'"
        stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=10)
        output = stdout.read().decode('utf-8').strip()
        return [json.loads(line) for line in output.splitlines() if line.strip().startswith("{")]

    def get_network_journal_logs(self, ssh_client):
        cmd = "journalctl -u systemd-networkd --since '-5 minutes' --no-pager"
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        return stdout.read().decode('utf-8').strip()

    def collect_network_info(self, device):
        primary_ip_field = device.get('primary_ip', {}).get('address')
        if not primary_ip_field:
            print(f"Устройство {device.get('name')} не имеет primary_ip")
            return None
        host_ip = primary_ip_field.split('/')[0]
        ssh_user = device.get('custom_fields', {}).get('ssh_user', 'root')
        ssh_password = device.get('custom_fields', {}).get('ssh_password', None)
        key_filename = None

        print(f"Подключаюсь к {host_ip} как {ssh_user}")
        try:
            ssh_client = self.ssh_connect(host_ip, ssh_user, password=ssh_password, key_filename=key_filename)
        except Exception as e:
            print(f"Не удалось подключиться по SSH к {host_ip}: {e}")
            return None

        host_snapshot = self.get_host_network_snapshot(ssh_client)
        docker_snapshot = self.get_docker_network_info(ssh_client)
        docker_events = self.get_docker_events(ssh_client)
        journal_logs = self.get_network_journal_logs(ssh_client)
        ssh_client.close()

        result = {
            'device': device,
            'host_snapshot': host_snapshot,
            'docker_snapshot': docker_snapshot,
            'docker_events': docker_events,
            'network_journal': journal_logs,
            'timestamp': time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        return result

    def collect_all(self):
        #devices = self.get_devices_from_netbox()
        devices = [
            {
                'name': 'server-01',
                'primary_ip': {
                    'address': '192.168.122.43'
                },
                'custom_fields': {
                    'ssh_user': 'netboxagent',
                    'ssh_password': 'MySecurePass'
                }
            }
        ]
        all_data = []
        for device in devices:
            info = self.collect_network_info(device)
            filename = f"json_data/01_{device.get('name')}_coll.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=4)
                print(f"Saved to {filename}")
            if info:
                all_data.append(info)
        return all_data

def collect_for_device(device):
    collector = NetworkCollector(netbox_url="http://netbox.local", netbox_token="YOUR_NETBOX_TOKEN")
    return collector.collect_network_info(device)
