from flask import Flask, request, render_template, jsonify
import requests
from datetime import timedelta
import urllib3
import logging

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

PROXMOX_URL = "https://192.168.1.252:8006/api2/json"
TOKEN_ID = "pythonapi@pam!apipython"
TOKEN_SECRET = "8b13892c-c6e9-43c0-b128-3f17dd0f932a"
headers = {
    'Authorization': f'PVEAPIToken={TOKEN_ID}={TOKEN_SECRET}',
    'Content-Type': 'application/json'
}

@app.route('/', methods=['GET', 'POST'])
def home():
    return render_template('index.html')

@app.route('/get_vm_data/<int:vm_id>', methods=['GET'])
def get_vm_data(vm_id):
    """Fetch VM/container data for the given VM ID."""
    node = "innprox-02"  # Hardcoded node name

    # Try fetching QEMU VM data
    qemu_url = f"{PROXMOX_URL}/nodes/{node}/qemu/{vm_id}/status/current"
    qemu_response = requests.get(qemu_url, headers=headers, verify=False)
    logger.info(f"QEMU response status: {qemu_response.status_code}, data: {qemu_response.text}")

    if qemu_response.status_code == 200:
        # If QEMU VM data is found, process it
        status_data = qemu_response.json()['data']
        vm_type = "qemu"
        config_url = f"{PROXMOX_URL}/nodes/{node}/qemu/{vm_id}/config"
    else:
        # If QEMU VM data is not found, try fetching LXC container data
        lxc_url = f"{PROXMOX_URL}/nodes/{node}/lxc/{vm_id}/status/current"
        lxc_response = requests.get(lxc_url, headers=headers, verify=False)
        logger.info(f"LXC response status: {lxc_response.status_code}, data: {lxc_response.text}")

        if lxc_response.status_code == 200:
            # If LXC container data is found, process it
            status_data = lxc_response.json()['data']
            vm_type = "lxc"
            config_url = f"{PROXMOX_URL}/nodes/{node}/lxc/{vm_id}/config"
        else:
            # If neither QEMU nor LXC data is found, return an error
            return jsonify({"error": f"Failed to fetch VM/container status: {lxc_response.status_code}"}), 400

    rrd_response = requests.get(config_url, headers=headers, verify=False)
    if rrd_response.status_code != 200:
        return jsonify({"error": f"Failed to fetch RRD data: {rrd_response.status_code}"}), 400

    # Process RRD data
    rrd_data = rrd_response.json()['data']
    network_traffic = [0, 0]  # Default values for network traffic (in/out)
    disk_io = [0, 0]  # Default values for disk I/O (read/write)

    if isinstance(rrd_data, list) and len(rrd_data) > 0:
        last_entry = rrd_data[-1]
        if isinstance(last_entry, list) and len(last_entry) >= 8:
            network_traffic = [last_entry[4], last_entry[5]]  # Network traffic (in/out)
            disk_io = [last_entry[6], last_entry[7]]  # Disk I/O (read/write)

    # Process status and config data
    config_data = rrd_response.json()['data']
    vm_data = {
        "vmid": vm_id,
        "type": vm_type,  # Indicates whether it's a QEMU VM or LXC container
        "node": node,  # Node name
        "status": status_data['status'],
        "ha_state": status_data.get('ha', {}).get('state', 'none'),  # HA state
        "uptime": str(timedelta(seconds=status_data['uptime'])),  # Convert uptime to human-readable format
        "cpu_usage": f"{float(status_data.get('cpu', 0)) * 100:.2f}% of {status_data.get('cpus', 1)} CPU(s)",  # CPU usage
        "memory_usage": f"{int(status_data.get('mem', 0)) / (1024 ** 2):.2f} MiB of {int(status_data.get('maxmem', 0)) / (1024 ** 2):.2f} MiB",  # Memory usage
        "bootdisk_size": f"{int(config_data.get('size', 0)) / (1024 ** 3):.2f} GiB",  # Boot disk size
        "network_traffic": network_traffic,  # Network traffic (in/out)
        "disk_io": disk_io,  # Disk I/O (read/write)
    }

    # Add LXC-specific fields
    if vm_type == "lxc":
        vm_data["unprivileged"] = config_data.get('unprivileged', 'No')
        vm_data["swap_usage"] = f"{int(status_data.get('swap', 0)) / (1024 ** 2):.2f} MiB of {int(status_data.get('maxswap', 0)) / (1024 ** 2):.2f} MiB"  # SWAP usage

    return jsonify(vm_data)

if __name__ == '__main__':
    app.run(host='192.168.1.133', port=5001, debug=True)

