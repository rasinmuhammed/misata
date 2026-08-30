import numpy as np
import pandas as pd

from examples.network_intrusion_netflow import (
    ATTACK_WEIGHTS,
    build,
    verify,
)


def test_full_verify_suite_passes():
    tables = build(n_hosts=300, n_flows=6000, seed=21)
    assert verify(tables) is True


def test_attack_composition_matches_declared_weights():
    tables = build(n_hosts=300, n_flows=8000, seed=22)
    measured = tables["flows"]["attack_cat"].value_counts(normalize=True)
    for cat, declared in ATTACK_WEIGHTS.items():
        assert abs(float(measured.get(cat, 0.0)) - declared) < max(0.01, declared * 0.3)


def test_port_scan_is_a_bare_single_packet_syn():
    tables = build(n_hosts=300, n_flows=6000, seed=23)
    flows = tables["flows"]
    scan = flows[flows["attack_cat"] == "port_scan"]
    assert (scan["packet_count"] == 1).all()
    assert scan["byte_count"].between(40, 60).all()
    assert (scan["protocol"] == "TCP").all()


def test_ddos_converges_on_very_few_targets():
    tables = build(n_hosts=300, n_flows=8000, seed=24)
    ddos = tables["flows"][tables["flows"]["attack_cat"] == "ddos"]
    assert ddos["dst_host_id"].nunique() <= 2
    assert ddos["src_host_id"].nunique() > 30


def test_dns_exfiltration_stays_on_real_dns_transport_but_oversized():
    tables = build(n_hosts=300, n_flows=8000, seed=25)
    flows = tables["flows"]
    exfil = flows[flows["attack_cat"] == "dns_exfiltration"]
    benign_dns = flows[(flows["attack_cat"] == "benign") & (flows["dst_port"] == 53)]
    assert (exfil["protocol"] == "UDP").all()
    assert (exfil["dst_port"] == 53).all()
    exfil_bpp = (exfil["byte_count"] / exfil["packet_count"]).mean()
    benign_bpp = (benign_dns["byte_count"] / benign_dns["packet_count"]).mean()
    assert exfil_bpp > benign_bpp * 1.3


def test_brute_force_repeats_against_few_pairs():
    tables = build(n_hosts=300, n_flows=8000, seed=26)
    flows = tables["flows"]
    brute = flows[flows["attack_cat"] == "brute_force"]
    assert (brute["protocol"] == "TCP").all()
    assert brute["dst_port"].isin([22, 3389]).all()
    pairs = brute.groupby(["src_host_id", "dst_host_id"]).size()
    assert pairs.mean() > 5


def test_no_flow_implies_an_impossible_sub_40_byte_packet():
    tables = build(n_hosts=300, n_flows=6000, seed=27)
    flows = tables["flows"]
    bytes_per_packet = flows["byte_count"] / flows["packet_count"]
    assert (bytes_per_packet >= 40).all()


def test_host_ip_addresses_respect_their_declared_zone():
    tables = build(n_hosts=300, n_flows=4000, seed=28)
    hosts = tables["hosts"]
    internal = hosts[hosts["zone"] == "internal"]
    external = hosts[hosts["zone"] == "external"]
    assert internal["ip_address"].str.startswith("10.").all()
    assert not external["ip_address"].str.match(r"^(10|127|172|169|192|0)\.").any()


def test_start_time_has_no_sub_millisecond_precision():
    tables = build(n_hosts=300, n_flows=4000, seed=29)
    ts = tables["flows"]["start_time"]
    assert (pd.DatetimeIndex(ts).floor("ms") == ts).all()


def test_no_flow_has_a_host_talking_to_itself():
    tables = build(n_hosts=300, n_flows=6000, seed=30)
    flows = tables["flows"]
    assert (flows["src_host_id"] != flows["dst_host_id"]).all()


def test_no_orphan_foreign_keys():
    tables = build(n_hosts=300, n_flows=6000, seed=31)
    hosts, flows = tables["hosts"], tables["flows"]
    assert flows["src_host_id"].isin(hosts["host_id"]).all()
    assert flows["dst_host_id"].isin(hosts["host_id"]).all()
