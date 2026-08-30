---
title: "Generate Synthetic Network Intrusion / Netflow Data in Python | Misata"
description: "Generate labeled netflow-style traffic with attack injection grounded in the ID2T / UNSW-NB15 construction methodology and named MITRE ATT&CK techniques (T1595, T1498, T1048.003, T1110). No real packet capture required, and no privacy problem to anonymize away."
---

# Generate Synthetic Network Intrusion / Netflow Data in Python

Security researchers openly complain that the standard intrusion-detection benchmarks are stale and keep getting reused anyway "because nothing better exists" — NSL-KDD dates to 1999, CICIDS2017 to 2017. Entire dedicated tools (ID2T, AIT Netflow, HIKARI-2021) exist purely to make fresher ones. A `protocol` column and an `is_attack` flag with no statistical relationship between them doesn't help: a port scan, a DDoS flood, and a brute-force attempt each carry a specific, checkable signature in packet size, byte count, and source/destination fan pattern, and a labeled dataset is only useful for testing an IDS if that signature is actually present in the data, not just named in a column.

```python
import misata

schema = {
    "hosts": {
        "__rows__": 500,
        "host_id": {"type": "integer", "primary_key": True},
        "zone": {"type": "string", "enum": ["internal", "external"], "weights": [0.30, 0.70]},
    },
    "flows": {
        "__rows__": 20000,
        "flow_id": {"type": "integer", "primary_key": True},
        "src_host_id": {"type": "integer", "foreign_key": {"table": "hosts", "column": "host_id"}},
        "dst_host_id": {"type": "integer", "foreign_key": {"table": "hosts", "column": "host_id"}},
        # Real attack category weights, not equal-probability placeholders.
        "attack_cat": {"type": "string",
            "enum": ["benign", "port_scan", "ddos", "dns_exfiltration", "brute_force"],
            "weights": [0.80, 0.12, 0.03, 0.02, 0.03]},
    },
}
tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=13))
print(list(tables.keys()))   # ['hosts', 'flows']
```

That is the minimal shape. The full example — IP addresses shaped to each host's declared zone, per-service traffic profiles, and each attack category built to carry its named technique's actual statistical signature — is a working, runnable script: [`examples/network_intrusion_netflow.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/network_intrusion_netflow.py). Run it directly:

```bash
python examples/network_intrusion_netflow.py
```

It prints every guarantee below, checked against the data it just generated:

```
hosts: 500  flows: 20000
attack_cat counts: {'benign': 16039, 'port_scan': 2348, 'brute_force': 610, 'ddos': 593, 'dns_exfiltration': 410}

  [OK] 'benign' is 0.802 of flows (declared 0.800)
  [OK] 'port_scan' is 0.117 of flows (declared 0.120)
  [OK] 'ddos' is 0.030 of flows (declared 0.030)
  [OK] 'dns_exfiltration' is 0.021 of flows (declared 0.020)
  [OK] 'brute_force' is 0.030 of flows (declared 0.030)
  [OK] label matches attack_cat on every row
  [OK] port_scan carries exactly 1 packet per flow (a bare SYN, no reply)
  [OK] port_scan frames are 40-60 bytes (minimal TCP SYN, no payload)
  [OK] port_scan hosts each hit 469 distinct ports vs 9.8 for an ordinary benign host
  [OK] ddos flows converge on exactly 2 targets
  [OK] ddos flows originate from 289 distinct sources (a wide botnet, not a single attacker)
  [OK] ddos per-flow packet count stays small (1-3; the flood is in flow count, not size)
  [OK] dns_exfiltration is 100% UDP/port 53, like any real DNS traffic
  [OK] dns_exfiltration averages 179 bytes/packet vs 80 for ordinary DNS queries
  [OK] brute_force targets only SSH (22) or RDP (3389), all TCP
  [OK] brute_force averages 34 flows per attacker/target pair vs 1.1 for benign traffic
  [OK] no flow implies an impossible sub-40-byte-per-packet frame
  [OK] flows.src_host_id and dst_host_id have zero orphans
  [OK] every host_id in hosts is unique
  [OK] internal hosts carry RFC 1918 (10.0.0.0/8) addresses
  [OK] external hosts carry no private/loopback-range address
  [OK] start_time carries no sub-millisecond precision
  [OK] no flow has a host talking to itself

ALL CHECKS PASSED
```

## What each attack category is grounded in

**The overall construction.** Protocol-realistic background traffic with attacks injected against documented behavior patterns and known ground-truth labels is the ID2T / UNSW-NB15 methodology (Cyber Range Lab, Australian Centre for Cyber Security). UNSW-NB15's own two-column convention — a binary `label` plus a multi-class `attack_cat` — is why this example ships both, rather than only one.

**Port scan (MITRE ATT&CK T1595, Active Scanning).** A real SYN scan leaves a specific fingerprint: a single bare TCP SYN packet (`packet_count = 1`), a minimal 40-60 byte frame with no payload, no completed handshake, and — the actual tell — one or a handful of source hosts hitting a huge, largely non-repeating spread of destination ports against very few targets. This example generates exactly that spread and checks it: scanning hosts hit roughly 50x more distinct ports than an ordinary benign host does.

**DDoS (MITRE ATT&CK T1498, Network Denial of Service).** A flood's signature isn't a large packet — it's concentration. Each individual flow here is small (1-3 packets), but a wide, distinct pool of external sources (a simulated botnet) all converge on the same one or two internal targets, checked directly: dozens of distinct sources, at most two distinct destinations.

**DNS exfiltration (MITRE ATT&CK T1048.003, Exfiltration Over DNS).** Forced to the real transport — UDP, port 53, exactly like any legitimate DNS query — because the only way to exfiltrate data through DNS is to look like DNS. What gives it away, and what this example actually measures, is payload size: exfiltrated data has to be encoded into the query itself, so its average bytes-per-packet runs well above an ordinary DNS lookup's, checked as a direct ratio against this same dataset's own benign DNS traffic rather than an assumed constant.

**Brute force (MITRE ATT&CK T1110, Brute Force).** Scoped to the two services it actually targets in practice — SSH (22) and RDP (3389) — with short flows sized like a failed authentication handshake, repeated from a small attacker pool against a small target pool far more densely than any benign traffic pattern: dozens of flows per attacker/target pair here, against roughly one for ordinary traffic.

## Giveaways caught before shipping

The [credit-risk-portfolio example](credit-risk.md) shipped once with unrounded floats and a nanosecond-precision date column. This one was built with those exact failure modes in mind from the start: `start_time` is floored to millisecond precision (a real netflow collector's actual resolution, not pandas' nanosecond default), IP addresses are shaped to each host's declared zone (internal hosts get RFC 1918 `10.x.x.x` addresses, external hosts get addresses outside every private and loopback range), no flow has a host talking to itself, and every packet/byte combination is checked against the physical floor of a real frame — no flow implies a sub-40-byte packet, which a pair of independently random integer columns would produce constantly.

## What this is not

This targets the four attack categories above, generated to carry their real statistical signature — it is not a general-purpose IDS training corpus covering every category UNSW-NB15 or CICIDS2017 label (backdoors, exploits, worms, and several others aren't modeled here). The traffic volumes and host counts are declared, not measured from a real network's actual baseline load. This is built for testing detection logic and validating a pipeline's handling of labeled netflow data, not as a drop-in replacement for a production SOC's live traffic feed.
