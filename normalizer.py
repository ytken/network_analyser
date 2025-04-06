import json, re
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime

class PrimaryIP(BaseModel):
    address: str

class Device(BaseModel):
    name: str
    id: Optional[int]
    role: Optional[Dict[str, str]]
    primary_ip: PrimaryIP

class HostSnapshot(BaseModel):
    interfaces: Optional[str]
    routes: Optional[str]
    sockets: Optional[str]
    iptables: Optional[str]
    hostname: Optional[str]

class DockerSnapshot(BaseModel):
    Id: str
    Created: str
    State: Dict[str, Any]
    Name: str
    NetworkSettings: Dict[str, Any]

class NetworkCollectorOutput(BaseModel):
    device: Device
    host_snapshot: HostSnapshot
    docker_snapshot: Dict[str, List[DockerSnapshot]]
    docker_events: Any
    network_journal: Any
    timestamp: str

class NetworkNormalizer:
    def parse_interfaces(self, raw):
        interfaces = []
        current = {}
        for line in raw.splitlines():
            if re.match(r'^\d+:', line):  # Новое устройство
                if current:
                    interfaces.append(current)
                parts = line.split(": ", 2)
                if len(parts) >= 2:
                    index_name = parts[1]
                    name = index_name.split()[0]
                    current = {"name": name, "inet": [], "inet6": []}
            elif "inet " in line:
                ip = line.strip().split()[1]
                current["inet"].append(ip)
            elif "inet6 " in line:
                ip6 = line.strip().split()[1]
                current["inet6"].append(ip6)
        if current:
            interfaces.append(current)
        return interfaces

    def parse_routes(self, raw):
        routes = []
        for line in raw.splitlines():
            parts = line.strip().split()
            if not parts:
                continue
            route = {"dst": parts[0]}
            if "via" in parts:
                route["via"] = parts[parts.index("via") + 1]
            if "dev" in parts:
                route["dev"] = parts[parts.index("dev") + 1]
            routes.append(route)
        return routes

    def parse_sockets(self, raw):
        sockets = []
        lines = raw.splitlines()
        if not lines:
            return sockets
        header = lines[0]
        for line in lines[1:]:
            if not line.strip():
                continue
            tokens = line.split()
            protocol = tokens[0]
            local = tokens[4]
            process = " ".join(tokens[6:])
            sockets.append({
                "protocol": protocol,
                "local_address": local,
                "process": process
            })
        return sockets

    def parse_iptables(self, raw: str) -> dict:
        if "password is required" in raw or "sudo:" in raw:
            return {"error": "Cannot read iptables: sudo failed or password prompt required."}

        chains = {}
        current_chain = None
        columns = []

        for line in raw.splitlines():
            line = line.strip()

            # Новая цепочка
            if line.startswith("Chain "):
                match = re.match(r"Chain (\S+) \(policy (\S+)(?: (\d+) packets, (\d+) bytes)?\)", line)
                if match:
                    chain_name, policy, packets, bytes_ = match.groups()
                    current_chain = chain_name
                    chains[current_chain] = {
                        "policy": policy,
                        "default_packets": int(packets) if packets else 0,
                        "default_bytes": int(bytes_) if bytes_ else 0,
                        "rules": []
                    }
                continue

            # Строка с названиями столбцов
            elif line.startswith("pkts") or line.startswith("target"):
                columns = re.split(r"\s{2,}", line)  # разделяем по двойному пробелу
                continue

            # Правило (если есть текущая цепочка)
            elif current_chain and line:
                # Убедимся, что line содержит хотя бы столбцы
                parts = re.split(r"\s{2,}", line)
                if len(parts) >= len(columns):
                    rule = dict(zip(columns, parts))
                    # Переименуем поля и приведём к нормальной структуре
                    chains[current_chain]["rules"].append({
                        "pkts": int(rule.get("pkts", 0)),
                        "bytes": int(rule.get("bytes", 0)),
                        "target": rule.get("target"),
                        "proto": rule.get("prot"),
                        "opt": rule.get("opt"),
                        "in": rule.get("in"),
                        "out": rule.get("out"),
                        "source": rule.get("source"),
                        "destination": rule.get("destination"),
                        "extra": parts[len(columns):]  # всё, что не поместилось — в отдельное поле
                    })

        return chains
    
    def parse_network_journal(self, raw: str):
        entries = []
        for line in raw.strip().splitlines():
            match = re.match(
                r"(?P<date>\w+\s+\d+\s+\d+:\d+:\d+)\s+(?P<host>\S+)\s+systemd-networkd\[\d+\]:\s+(?P<iface>\S+):\s+(?P<event>.+)",
                line
            )
            if match:
                date_str = match.group("date")
                # Преобразуем в ISO 8601 формат, дополнив год
                try:
                    timestamp = datetime.strptime(date_str + f" {datetime.now().year}", "%b %d %H:%M:%S %Y").isoformat()
                except ValueError:
                    timestamp = None
                entries.append({
                    "timestamp": timestamp,
                    "interface": match.group("iface"),
                    "event": match.group("event")
                })
        return entries

    def normalize(self, data):
        print("Отправка данных в модуль нормализации:")
        all_data = []
        for device in data:
            filtered_data = NetworkCollectorOutput.parse_obj(device).dict()
            filename = f"json_data/02_{filtered_data['device']['name']}_filt.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(filtered_data, f, ensure_ascii=False, indent=4)
                print(f"Saved to {filename}")
            normalized_data = filtered_data
            normalized_data["host_snapshot"]["interfaces"] = self.parse_interfaces(filtered_data["host_snapshot"]["interfaces"])
            normalized_data["host_snapshot"]["routes"] = self.parse_routes(filtered_data["host_snapshot"]["routes"])
            normalized_data["host_snapshot"]["sockets"] = self.parse_sockets(filtered_data["host_snapshot"]["sockets"])
            normalized_data["host_snapshot"]["iptables"] = self.parse_iptables(filtered_data["host_snapshot"]["iptables"])
            normalized_data["network_journal"] = self.parse_network_journal(filtered_data["network_journal"])
            filename = f"json_data/03_{normalized_data['device']['name']}_norm.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(normalized_data, f, ensure_ascii=False, indent=4)
                print(f"Saved to {filename}")
            if normalized_data:
                all_data.append(normalized_data)
        return all_data
