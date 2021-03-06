import os

import argparse
import glob
import json
import csv
import shutil

import datetime
import socket
import OpenSSL
import ssl

from snet_cli.mpe_client_command import MPEClientCommand
from snet_cli.mpe_service_command import MPEServiceCommand
from snet_cli.config import Config
from snet.snet_cli.utils import bytes32_to_str


class CustomArgs:
    def __init__(self):
        self.key = None
        self.value = None
        self.org_id = "snet"
        self.service_id = "example-service"
        self.from_block = 0
        self.group_name = None
        self.multipartyescrow_at = None
        self.only_id = False
        self.print_traceback = False
        self.registry_at = None
        self.sender = None
        self.wallet_index = None
        self.max_price = 1000000000
        self.yes = True


def get_metadata(dst_dir="./", network="mainnet"):
    conf = Config()
    conf.set_session_network(network, out_f=None)
    m = MPEClientCommand(conf, CustomArgs())
    s = MPEServiceCommand(conf, CustomArgs())
    org_id_list = ["snet", "mozi"]
    for org_id in org_id_list:
        print("Getting services from '{}'".format(org_id))
        (_, _, _, _, _, serviceNames, _) = m._getorganizationbyid(org_id=org_id)
        for idx, name in enumerate(serviceNames):
            name = bytes32_to_str(name)
            s.args.org_id = org_id
            s.args.service_id = name
            metadata = s._get_service_metadata_from_registry()
            file_path = "{}{}_{}.json".format(dst_dir, org_id, name)
            with open(file_path, "w") as fp:
                idx += 1
                print("{:03} - Saving {}...".format(idx, file_path))
                json.dump(metadata.m, fp=fp, indent=2)


def _get_not_after(hostname, port):
    try:
        socket.setdefaulttimeout(10)
        cert = ssl.get_server_certificate((hostname, port))
        x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert.encode())
        not_after = x509.get_notAfter()
        return datetime.datetime.strptime(not_after.decode(), "%Y%m%d%H%M%SZ")
    except KeyboardInterrupt:
        raise
    except:
        return


def check(hostname, check_443=False, start_port=7000, port_range=1):
    ret_list = dict()
    now = datetime.datetime.now()
    if check_443:
        not_after = _get_not_after(hostname=hostname, port=443)
        if not_after:
            ret_list[hostname + ":443"] = (not_after - now).days
    for p in range(port_range):
        port = start_port + p
        not_after = _get_not_after(hostname=hostname, port=port)
        if not_after:
            expiring = (not_after - now).days
            ret_list[hostname + ":" + str(port)] = expiring
            print("    └───── {}:{} [{} days]".format(hostname, port, expiring))
        else:
            print("    └───── {}:{} [Fail]".format(hostname, port))
    return ret_list


def run(src_dir, network, update):
    if src_dir[-1] != "/":
        src_dir += "/"
    if update:
        if os.path.exists(src_dir):
            shutil.rmtree(src_dir)
        os.makedirs(src_dir)
        # Getting all Services" metadata from Registry
        get_metadata(src_dir, network)

    services_d = dict()
    report = []
    s_list = glob.glob("{}*.json".format(src_dir))
    for s in s_list:
        try:
            with open(s, "r") as f:
                j = json.load(f)
                s_name = s.split("/")[-1].replace(".json", "")
                services_d[s_name] = dict()
                services_d[s_name]["endpoints"] = dict()
                services_d[s_name]["contributors"] = dict()
                print("Processing {}".format(s_name))
                for g in j["groups"]:
                    for e in g["endpoints"]:
                        if e not in services_d[s_name]["endpoints"]:
                            hostname = e.replace("https://", "")
                            [hostname, port] = hostname.split(":")
                            exp_days = check(hostname=hostname, start_port=int(port))
                            if exp_days:
                                services_d[s_name]["endpoints"][e] = exp_days[hostname + ":" + port]
                            else:
                                services_d[s_name]["endpoints"][e] = -1
                contrib_list = j.get("contributors", [])
                if not contrib_list:
                    services_d[s_name]["contributors"]["NoName"] = "NoEmail"
                for c in contrib_list:
                    name = c.get("name", None)
                    email = c.get("email_id", None)
                    if name and name not in services_d[s_name]["contributors"]:
                        services_d[s_name]["contributors"][name] = email
                for e, dt in services_d[s_name]["endpoints"].items():
                    lines = [(s.split("/")[-1].replace(".json", ""),
                             name,
                             email,
                             e, dt) for name, email in services_d[s_name]["contributors"].items()]
                    report.extend(lines)
        except Exception as e:
            print("[ERROR]", str(e))
            continue
    return services_d, sorted(report, key=lambda x: x[4])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src",
                        type=str,
                        default=os.environ.get("SNET_CHECK_SRC_DIR", "./"),
                        help="Source directory with services' metadata.")
    parser.add_argument("-net", "--network",
                        type=str,
                        default=os.environ.get("SNET_CHECK_NETWORK", "mainnet"),
                        help="The Ethereum network (mainnet, ropsten, etc)")
    parser.add_argument("-u", "--update",
                        action="store_true",
                        help="Get all services from Registry.")
    parser.add_argument("-o", "--csv_output",
                        type=str,
                        default=os.environ.get("SNET_CHECK_OUTPUT", "services_report.csv"),
                        help="CSV filename to save the report.")
    args = parser.parse_args()
    _, report = run(args.src, args.network, args.update)
    if args.csv_output:
        print("Saving report to {}".format(args.csv_output))
        with open(args.csv_output, "w") as fp:
            csv_writer = csv.writer(fp)
            header = ["ServiceName", "Contributor", "Email", "Endpoint", "Expiration(days)"]
            csv_writer.writerow(header)
            for line in report:
                csv_writer.writerow(line)


if __name__ == "__main__":
    main()
