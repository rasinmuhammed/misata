"""
Labeled netflow-style network traffic: hosts and flows, with attack traffic
injected against the same construction methodology security researchers
actually use to build intrusion-detection benchmarks -- not independently
randomized port/byte/duration columns with a "malicious" flag stapled on.

Every attack archetype below traces to a named, citable source:

  * The overall approach -- protocol-realistic background traffic with
    attacks injected against documented behavior patterns and known
    ground-truth labels -- is the ID2T / UNSW-NB15 construction methodology
    (Cyber Range Lab, Australian Centre for Cyber Security). UNSW-NB15's own
    column layout is the reason this example ships both a binary `label`
    (benign/malicious) and a multi-class `attack_cat`, rather than only one.

  * Each attack category is grounded in a specific MITRE ATT&CK technique
    ID, and generated to actually carry that technique's real statistical
    signature -- not just labeled with its name:
      - port_scan     -> T1595 Active Scanning: a single bare TCP SYN
                          (packet_count=1, ~40-60 byte frame, no reply)
                          against a wide, largely non-repeating spread of
                          destination ports -- the exact fingerprint an
                          nmap SYN scan leaves in netflow data.
      - ddos          -> T1498 Network Denial of Service: a wide fan-in of
                          distinct external sources onto a tiny handful of
                          targets, each flow itself small (1-3 packets),
                          because a flood's signature is concentration, not
                          per-flow size.
      - dns_exfiltration -> T1048.003 Exfiltration Over DNS: forced to
                          protocol UDP / port 53 like any DNS traffic, but
                          with a materially larger per-packet payload than a
                          normal DNS query carries, because exfiltrated data
                          has to be encoded into the query itself.
      - brute_force   -> T1110 Brute Force: many short, repeated flows
                          between the same small attacker/target pairs on
                          SSH (22) or RDP (3389), each one the size of a
                          failed authentication handshake.

What this earns, checked below: an attack category isn't a label sitting
next to random numbers. Each one measurably carries the real statistical
signature security tooling actually keys on -- packet count, byte-per-
packet size, port spread, and source/destination fan patterns -- and the
whole thing reconciles to declared, checkable rates.
"""

import numpy as np
import pandas as pd

import misata

RNG_SEED = 13

# Declared composition. Security researchers openly complain that the
# standard benchmarks (NSL-KDD from 1999, CICIDS2017) are stale and reused
# anyway "because nothing better exists" -- this is the shape a fresh,
# labeled netflow dataset for IDS testing is expected to have.
ATTACK_WEIGHTS = {
    "benign": 0.80,
    "port_scan": 0.12,
    "ddos": 0.03,
    "dns_exfiltration": 0.02,
    "brute_force": 0.03,
}

MITRE_TECHNIQUE = {
    "port_scan": "T1595",
    "ddos": "T1498",
    "dns_exfiltration": "T1048.003",
    "brute_force": "T1110",
}

# Typical average payload size per well-known service port, in bytes at the
# IP layer -- DNS queries are small (~60-90B), SSH/RDP handshakes moderate,
# web traffic large. This is what makes a "benign DNS query" and a "DNS
# exfiltration query" comparable on the same axis instead of apples-to-oranges.
PORT_AVG_PACKET_BYTES = {
    80: 850, 443: 900, 53: 75, 25: 500, 22: 300,
    3389: 400, 8080: 850, 3306: 400, 993: 500, 21: 300,
}
PORT_WEIGHTS = {
    80: 0.28, 443: 0.30, 53: 0.15, 25: 0.05, 22: 0.05,
    3389: 0.03, 8080: 0.05, 3306: 0.03, 993: 0.03, 21: 0.03,
}


def _random_ipv4(rng: np.random.Generator, n: int, private: bool) -> list:
    if n == 0:
        return []
    if private:
        # RFC 1918: 10.0.0.0/8, the block most corporate internal networks use.
        a = np.full(n, 10)
        b = rng.integers(0, 256, n)
        c = rng.integers(0, 256, n)
    else:
        # A public-looking first octet, excluding private (10, 172.16-31,
        # 192.168), loopback (127), and this-network (0) blocks. 172 is
        # dropped wholesale for simplicity rather than carving out just its
        # private /12 -- plenty of address space remains.
        pool = [x for x in range(1, 224) if x not in (0, 10, 127, 172, 169, 192)]
        a = rng.choice(pool, n)
        b = rng.integers(0, 256, n)
        c = rng.integers(0, 256, n)
    d = rng.integers(1, 255, n)
    return [f"{ai}.{bi}.{ci}.{di}" for ai, bi, ci, di in zip(a, b, c, d)]


def build(n_hosts: int = 500, n_flows: int = 20_000, seed: int = RNG_SEED):
    schema = {
        "hosts": {
            "__rows__": n_hosts,
            "host_id": {"type": "integer", "primary_key": True},
            # Most of the monitored estate is external (the wider internet
            # talking to a handful of internal services) -- realistic of
            # what a perimeter netflow sensor actually sees.
            "zone": {"type": "string", "enum": ["internal", "external"],
                      "weights": [0.30, 0.70]},
        },
        "flows": {
            "__rows__": n_flows,
            "flow_id": {"type": "integer", "primary_key": True},
            "src_host_id": {"type": "integer",
                             "foreign_key": {"table": "hosts", "column": "host_id"}},
            "dst_host_id": {"type": "integer",
                             "foreign_key": {"table": "hosts", "column": "host_id"}},
            "start_time": {"type": "datetime",
                             "min_date": "2026-06-01", "max_date": "2026-06-08"},
            "attack_cat": {"type": "string", "enum": list(ATTACK_WEIGHTS.keys()),
                             "weights": list(ATTACK_WEIGHTS.values())},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))
    return _reconcile(tables, seed)


def _reconcile(tables: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed + 1)

    # --- hosts: assign real-shaped IPs by zone -----------------------------
    hosts = tables["hosts"].copy()
    is_internal = (hosts["zone"] == "internal").to_numpy()
    ips = np.empty(len(hosts), dtype=object)
    ips[is_internal] = _random_ipv4(rng, int(is_internal.sum()), private=True)
    ips[~is_internal] = _random_ipv4(rng, int((~is_internal).sum()), private=False)
    hosts["ip_address"] = ips
    tables["hosts"] = hosts

    internal_ids = hosts.loc[is_internal, "host_id"].to_numpy()
    external_ids = hosts.loc[~is_internal, "host_id"].to_numpy()
    all_ids = hosts["host_id"].to_numpy()

    # --- designated pools per archetype (deterministic given the seed) ----
    # Real attack traffic doesn't come from everywhere at once: a scan comes
    # from a handful of scanning hosts against a handful of targets, a DDoS
    # fans in from many sources onto very few, etc. Fixing small pools here
    # is what makes the fan-in/fan-out signatures checkable below, instead
    # of just being randomly diffuse and unfalsifiable.
    portscan_scanners = rng.choice(external_ids, size=min(5, len(external_ids)), replace=False)
    portscan_targets = rng.choice(internal_ids, size=min(2, len(internal_ids)), replace=False)
    ddos_targets = rng.choice(internal_ids, size=min(2, len(internal_ids)), replace=False)
    dns_infected = rng.choice(internal_ids, size=min(8, len(internal_ids)), replace=False)
    dns_c2 = rng.choice(external_ids, size=min(3, len(external_ids)), replace=False)
    bf_attackers = rng.choice(external_ids, size=min(6, len(external_ids)), replace=False)
    bf_targets = rng.choice(internal_ids, size=min(3, len(internal_ids)), replace=False)

    flows = tables["flows"].copy()
    n = len(flows)
    attack = flows["attack_cat"].to_numpy()

    src = np.zeros(n, dtype=np.int64)
    dst = np.zeros(n, dtype=np.int64)
    protocol = np.empty(n, dtype=object)
    src_port = np.zeros(n, dtype=np.int64)
    dst_port = np.zeros(n, dtype=np.int64)
    packet_count = np.zeros(n, dtype=np.int64)
    byte_count = np.zeros(n, dtype=np.int64)
    duration_ms = np.zeros(n, dtype=np.int64)

    def _fill(mask, s, d, proto, sport, dport, pkts, bytes_per_pkt):
        k = int(mask.sum())
        if k == 0:
            return
        src[mask] = s(k)
        dst[mask] = d(k)
        protocol[mask] = proto(k) if callable(proto) else proto
        src_port[mask] = sport(k) if callable(sport) else sport
        dst_port[mask] = dport(k) if callable(dport) else dport
        packet_count[mask] = pkts(k) if callable(pkts) else pkts
        byte_count[mask] = np.round(packet_count[mask] * bytes_per_pkt(k)).astype(np.int64)

    # --- benign: ordinary internal-to-anywhere service traffic ------------
    m = attack == "benign"
    ports = rng.choice(list(PORT_WEIGHTS.keys()), size=int(m.sum()), p=list(PORT_WEIGHTS.values()))
    avg_bytes = np.array([PORT_AVG_PACKET_BYTES[p] for p in ports])
    _fill(
        m,
        s=lambda k: rng.choice(internal_ids, size=k),
        d=lambda k: rng.choice(all_ids, size=k),
        proto=lambda k: rng.choice(["TCP", "UDP", "ICMP"], size=k, p=[0.70, 0.25, 0.05]),
        sport=lambda k: rng.integers(1024, 65536, size=k),
        dport=lambda k: ports,
        pkts=lambda k: np.clip(rng.lognormal(mean=3.0, sigma=0.9, size=k), 1, None).round().astype(np.int64),
        bytes_per_pkt=lambda k: np.clip(rng.lognormal(mean=np.log(avg_bytes), sigma=0.35), 40, 1500),
    )
    duration_ms[m] = np.clip(rng.lognormal(mean=7.0, sigma=1.3, size=int(m.sum())), 1, None).round().astype(np.int64)

    # --- port_scan: T1595, a bare SYN spread across many ports ------------
    m = attack == "port_scan"
    _fill(
        m,
        s=lambda k: rng.choice(portscan_scanners, size=k),
        d=lambda k: rng.choice(portscan_targets, size=k),
        proto="TCP",
        sport=lambda k: rng.integers(1024, 65536, size=k),
        dport=lambda k: rng.integers(1, 65536, size=k),
        pkts=lambda k: np.ones(k, dtype=np.int64),
        bytes_per_pkt=lambda k: rng.integers(40, 61, size=k),
    )
    duration_ms[m] = rng.integers(1, 6, size=int(m.sum()))

    # --- ddos: T1498, wide fan-in of small floods onto few targets --------
    m = attack == "ddos"
    _fill(
        m,
        s=lambda k: rng.choice(external_ids, size=k),
        d=lambda k: rng.choice(ddos_targets, size=k),
        proto="UDP",
        sport=lambda k: rng.integers(1024, 65536, size=k),
        dport=lambda k: rng.choice([80, 53], size=k, p=[0.7, 0.3]),
        pkts=lambda k: rng.integers(1, 4, size=k),
        bytes_per_pkt=lambda k: rng.integers(40, 101, size=k),
    )
    duration_ms[m] = rng.integers(1, 11, size=int(m.sum()))

    # --- dns_exfiltration: T1048.003, oversized queries to a C2 resolver --
    m = attack == "dns_exfiltration"
    _fill(
        m,
        s=lambda k: rng.choice(dns_infected, size=k),
        d=lambda k: rng.choice(dns_c2, size=k),
        proto="UDP",
        sport=lambda k: rng.integers(1024, 65536, size=k),
        dport=53,
        pkts=lambda k: rng.integers(2, 6, size=k),
        bytes_per_pkt=lambda k: np.clip(rng.normal(180, 35, size=k), 130, 320),
    )
    duration_ms[m] = rng.integers(20, 121, size=int(m.sum()))

    # --- brute_force: T1110, repeated short failed-auth attempts ----------
    m = attack == "brute_force"
    _fill(
        m,
        s=lambda k: rng.choice(bf_attackers, size=k),
        d=lambda k: rng.choice(bf_targets, size=k),
        proto="TCP",
        sport=lambda k: rng.integers(1024, 65536, size=k),
        dport=lambda k: rng.choice([22, 3389], size=k, p=[0.65, 0.35]),
        pkts=lambda k: rng.integers(4, 9, size=k),
        bytes_per_pkt=lambda k: rng.integers(60, 151, size=k),
    )
    duration_ms[m] = rng.integers(200, 801, size=int(m.sum()))

    # No host talks to itself: a benign flow that happened to draw the same
    # src and dst by chance gets a fresh destination instead.
    self_talk = src == dst
    if self_talk.any():
        replacement = rng.choice(all_ids, size=int(self_talk.sum()))
        still_bad = replacement == src[self_talk]
        while still_bad.any():
            replacement[still_bad] = rng.choice(all_ids, size=int(still_bad.sum()))
            still_bad = replacement == src[self_talk]
        dst[self_talk] = replacement

    # A real netflow collector timestamps at millisecond resolution, not
    # the nanosecond precision pandas defaults a "datetime" column to --
    # left alone, that's exactly the kind of giveaway a synthetic file
    # trips on (see the credit-risk-portfolio example's origination_date
    # writeup for the same lesson applied to a date column).
    flows["start_time"] = pd.DatetimeIndex(flows["start_time"]).floor("ms")

    flows["src_host_id"] = src
    flows["dst_host_id"] = dst
    flows["protocol"] = protocol
    flows["src_port"] = src_port
    flows["dst_port"] = dst_port
    flows["packet_count"] = packet_count
    flows["byte_count"] = byte_count
    flows["duration_ms"] = duration_ms
    # UNSW-NB15's own two-column convention: a binary flag any IDS baseline
    # trains against, and a multi-class category for anything finer-grained.
    flows["label"] = np.where(flows["attack_cat"] == "benign", "benign", "malicious")

    tables["flows"] = flows
    return tables


def verify(tables: dict) -> bool:
    hosts = tables["hosts"]
    flows = tables["flows"]
    checks = []

    # 1. Declared composition holds, measured from the rows themselves.
    measured = flows["attack_cat"].value_counts(normalize=True)
    for cat, declared in ATTACK_WEIGHTS.items():
        m = float(measured.get(cat, 0.0))
        ok = abs(m - declared) < max(0.01, declared * 0.25)
        checks.append((f"'{cat}' is {m:.3f} of flows (declared {declared:.3f})", ok))

    # 2. binary label agrees with attack_cat on every row.
    expected_label = np.where(flows["attack_cat"] == "benign", "benign", "malicious")
    checks.append(("label matches attack_cat on every row",
                    (flows["label"].to_numpy() == expected_label).all()))

    port_scan = flows[flows["attack_cat"] == "port_scan"]
    ddos = flows[flows["attack_cat"] == "ddos"]
    dns_exfil = flows[flows["attack_cat"] == "dns_exfiltration"]
    brute = flows[flows["attack_cat"] == "brute_force"]
    benign = flows[flows["attack_cat"] == "benign"]
    benign_dns = benign[benign["dst_port"] == 53]

    # 3. port_scan (T1595): a bare single-packet SYN, not a completed session.
    checks.append(("port_scan carries exactly 1 packet per flow (a bare SYN, no reply)",
                    (port_scan["packet_count"] == 1).all()))
    checks.append(("port_scan frames are 40-60 bytes (minimal TCP SYN, no payload)",
                    port_scan["byte_count"].between(40, 60).all()))

    # 4. port_scan sweeps a wide, largely non-repeating spread of ports --
    # this is the actual scan signature: many distinct dst_port values from
    # very few source hosts, unlike any benign traffic pattern.
    distinct_ports_per_scanner = port_scan.groupby("src_host_id")["dst_port"].nunique().mean()
    distinct_ports_per_benign_src = benign.groupby("src_host_id")["dst_port"].nunique().mean()
    checks.append((f"port_scan hosts each hit {distinct_ports_per_scanner:.0f} distinct ports "
                    f"vs {distinct_ports_per_benign_src:.1f} for an ordinary benign host",
                    distinct_ports_per_scanner > distinct_ports_per_benign_src * 5))

    # 5. ddos (T1498): the fan-in signature -- very few distinct targets,
    # a wide spread of distinct sources, each individual flow tiny.
    checks.append((f"ddos flows converge on exactly {ddos['dst_host_id'].nunique()} targets",
                    ddos["dst_host_id"].nunique() <= 2))
    checks.append((f"ddos flows originate from {ddos['src_host_id'].nunique()} distinct sources "
                    "(a wide botnet, not a single attacker)",
                    ddos["src_host_id"].nunique() > 50))
    checks.append(("ddos per-flow packet count stays small (1-3; the flood is in flow count, not size)",
                    ddos["packet_count"].between(1, 3).all()))

    # 6. dns_exfiltration (T1048.003): forced to real DNS transport, but
    # with a materially larger payload than an ordinary DNS query carries.
    checks.append(("dns_exfiltration is 100% UDP/port 53, like any real DNS traffic",
                    (dns_exfil["protocol"] == "UDP").all() and (dns_exfil["dst_port"] == 53).all()))
    exfil_bpp = (dns_exfil["byte_count"] / dns_exfil["packet_count"]).mean()
    benign_dns_bpp = (benign_dns["byte_count"] / benign_dns["packet_count"]).mean() if len(benign_dns) else float("nan")
    checks.append((f"dns_exfiltration averages {exfil_bpp:.0f} bytes/packet vs "
                    f"{benign_dns_bpp:.0f} for ordinary DNS queries",
                    exfil_bpp > benign_dns_bpp * 1.5))

    # 7. brute_force (T1110): the right target service, and the repeated-
    # attempt fan pattern (many flows crammed into very few attacker/target
    # pairs), not a diffuse one-off connection.
    checks.append(("brute_force targets only SSH (22) or RDP (3389), all TCP",
                    (brute["protocol"] == "TCP").all() and brute["dst_port"].isin([22, 3389]).all()))
    bf_pairs = brute.groupby(["src_host_id", "dst_host_id"]).size()
    benign_pairs = benign.groupby(["src_host_id", "dst_host_id"]).size()
    checks.append((f"brute_force averages {bf_pairs.mean():.0f} flows per attacker/target pair "
                    f"vs {benign_pairs.mean():.1f} for benign traffic (repeated attempts, not one-offs)",
                    bf_pairs.mean() > benign_pairs.mean() * 5))

    # 8. Internal physical-layer consistency: no flow's byte_count implies
    # an impossible sub-40-byte packet (the minimum a real TCP/IP frame
    # carries) -- a giveaway generic random byte/packet columns would miss.
    bytes_per_packet_all = flows["byte_count"] / flows["packet_count"]
    checks.append(("no flow implies an impossible sub-40-byte-per-packet frame",
                    (bytes_per_packet_all >= 40).all()))

    # 9. Structural guarantees.
    checks.append(("flows.src_host_id and dst_host_id have zero orphans",
                    flows["src_host_id"].isin(hosts["host_id"]).all()
                    and flows["dst_host_id"].isin(hosts["host_id"]).all()))
    checks.append(("every host_id in hosts is unique",
                    hosts["host_id"].is_unique))
    checks.append(("internal hosts carry RFC 1918 (10.0.0.0/8) addresses",
                    hosts.loc[hosts["zone"] == "internal", "ip_address"].str.startswith("10.").all()))
    checks.append(("external hosts carry no private/loopback-range address",
                    ~hosts.loc[hosts["zone"] == "external", "ip_address"]
                        .str.match(r"^(10|127|172|169|192|0)\.").any()))
    checks.append(("start_time carries no sub-millisecond precision (a real collector's resolution)",
                    (pd.DatetimeIndex(flows["start_time"]).floor("ms") == flows["start_time"]).all()))
    checks.append(("no flow has a host talking to itself",
                    (flows["src_host_id"] != flows["dst_host_id"]).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    tables = build(n_hosts=500, n_flows=20_000, seed=RNG_SEED)
    print(f"hosts: {len(tables['hosts'])}  flows: {len(tables['flows'])}")
    counts = tables["flows"]["attack_cat"].value_counts()
    print("attack_cat counts:", dict(counts))
    print()
    ok = verify(tables)
    print()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    raise SystemExit(0 if ok else 1)
