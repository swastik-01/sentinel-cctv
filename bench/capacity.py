"""Statewide capacity and cost model. Every sizing and cost number in docs/plan-for-scale.md
comes from here.

Every input says where it comes from, and the Inputs table at the end of the output lists them:
  GIVEN      - fixed: the problem statement, or the PoC's own configuration
  MEASURED   - from the PoC (`sentinel-bench`, `bench/matcher.py`, the PoC database), dated
  ASSUMPTION - planning values to be replaced by PoC measurements, site surveys or GeM quotes

    python bench/capacity.py                 # markdown tables, in Plan for Scale order
    python bench/capacity.py --anpr-share 0.15 --node-anpr-streams 48
    python bench/capacity.py --help          # every input with its label

On a cp1252 Windows console set PYTHONUTF8=1 first (the tables print ₹ and ≈).
"""
from __future__ import annotations

import argparse
import copy
import math
from types import SimpleNamespace

GIVEN, MEASURED, ASSUMPTION = "GIVEN", "MEASURED", "ASSUMPTION"

p = argparse.ArgumentParser(description="Statewide capacity and cost model. Each input's help "
                                        "says whether it is GIVEN, MEASURED or an ASSUMPTION.")
INPUTS: list[tuple[str, str, str, str]] = []   # (group, flag, kind, basis) for the Inputs table


def inputs(group: str, *specs: tuple) -> None:
    for flag, default, kind, basis in specs:
        p.add_argument(flag, type=type(default), default=default,
                       help=f"{kind}: {basis}".replace("%", "%%"))
        INPUTS.append((group, flag, kind, basis))


inputs("Fleet and tiers",
       ("--cameras", 80_000, GIVEN, "approximate statewide estate in the problem statement"),
       ("--departments", 26, GIVEN, "departments running CCTV today, per the problem statement"),
       ("--districts", 33, ASSUMPTION, "one edge site and one control room per district; Gujarat has 34 "
                                       "revenue districts since Vav-Tharad was carved out in 2025, so confirm "
                                       "against police districts and commissionerates"),
       ("--anpr-share", 0.10, ASSUMPTION, "share of cameras positioned for plate reads (tier A); the "
                                          "registry's anpr_viable replaces it"),
       ("--event-share", 0.20, ASSUMPTION, "share with low-rate event analytics, i.e. counts (tier B)"),
       ("--anpr-fps", 5.0, ASSUMPTION, "tier A analysis rate, the worker's target; the laptop achieved "
                                       "4.8 per stream at 1-2 streams (17 Sep)"),
       ("--event-fps", 1.0, ASSUMPTION, "tier B analysis rate, keyframes only"))
inputs("Edge and core compute",
       ("--node-anpr-streams", 60, ASSUMPTION, "1080p ANPR streams per 1-GPU edge node at 5 fps; the first "
                                               "thing the PoC measures (sentinel-bench)"),
       ("--node-event-streams", 250, ASSUMPTION, "keyframe-only sub-stream decodes per node at ~1 fps"),
       ("--headroom", 0.25, ASSUMPTION, "N+1 failover and growth"),
       ("--node-kw", 0.5, ASSUMPTION, "average draw of a 1-GPU 2U edge server under load"),
       ("--match-ms", 1.14, MEASURED, "median watchlist match per plate read not on the list, 100,000 "
                                      "entries, one connection (bench/results/matcher.md, 24 Sep)"))
inputs("Traffic and payloads",
       ("--vehicles-per-anpr-cam-day", 6_000, ASSUMPTION, "vehicles read per ANPR camera per day; real "
                                                          "junction counts replace it"),
       ("--sighting-row-bytes", 600, ASSUMPTION, "Postgres row + indexes; the PoC's populated partition holds "
                                                 "503 B per row incl. indexes (4,205 rows, 24 Sep)"),
       ("--spool-row-bytes", 400, MEASURED, "a sighting as the worker spools it (JSON): 399 B average over "
                                            "4,205 PoC sightings re-serialised in the sink's format, 24 Sep"),
       ("--crop-kb", 8.0, ASSUMPTION, "JPEG plate crop; the PoC's 4,187 crops average 6.2 KB (24 Sep)"),
       ("--count-window-s", 60, GIVEN, "PoC COUNT_WINDOW_S: one vehicle/person count row per camera per window"),
       ("--count-row-bytes", 600, MEASURED, "512 B busiest PoC count row + ~80 B of index"),
       ("--spool-count-bytes", 430, MEASURED, "a count row as the worker spools it (JSON): largest of 368 PoC "
                                              "rows re-serialised (331 B average), 24 Sep"),
       ("--wal-factor", 2.0, ASSUMPTION, "WAL bytes written per stored byte (indexes, full-page writes)"))
inputs("Retention and recovery",
       ("--hot-days", 90, ASSUMPTION, "sightings and counts kept in Postgres"),
       ("--crop-days", 30, ASSUMPTION, "plate crops kept at the edge"),
       ("--archive-years", 5, ASSUMPTION, "warm Parquet archive of sightings and counts on the object store"),
       ("--pitr-days", 14, ASSUMPTION, "point-in-time recovery window (WAL kept at DR)"),
       ("--backup-fulls", 2, ASSUMPTION, "weekly full base backups kept at DR"),
       ("--spool-mb", 512.0, GIVEN, "PoC SPOOL_MAX_MB: store-and-forward cap per worker"),
       ("--spool-days", 7, ASSUMPTION, "backhaul outage an edge node rides out without dropping sightings"),
       ("--model4-days", 15, ASSUMPTION, "central recording retention for the Model 4 comparison: the upper "
                                         "end of the 7-15 days departments keep today"))
inputs("Viewing and backbone",
       ("--state-rooms", 1, ASSUMPTION, "state-level control rooms, on top of one per district"),
       ("--tiles-per-room", 16, ASSUMPTION, "video-wall tiles per control room at peak"),
       ("--preview-mbps", 0.8, ASSUMPTION, "640p H.264 preview (the camera's sub-stream); also tier B's "
                                           "analysis input"),
       ("--main-mbps", 4.0, ASSUMPTION, "1080p main stream; the PoC caps its real-footage clips at 4 Mbps"),
       ("--fullres-share", 0.1, ASSUMPTION, "tiles opened at full resolution"),
       ("--district-link-mbps", 50, ASSUMPTION, "each backhaul link per district"),
       ("--links-per-district", 2, ASSUMPTION, "two carriers, so one link can fail"))
inputs("Costs (₹ lakh)",
       ("--node-cost-lakh", 15.0, ASSUMPTION, "1-GPU edge server incl. storage; GeM quote needed"),
       ("--gpu-card-lakh", 4.0, ASSUMPTION, "the GPU's share of the node price"),
       ("--gpu-refresh-years", 5, ASSUMPTION, "accelerator replacement cycle"),
       ("--amc-pct", 8.0, ASSUMPTION, "annual maintenance, % of hardware capex, once warranty ends"),
       ("--warranty-years", 3, ASSUMPTION, "OEM warranty bought with the hardware"),
       ("--tariff-rs-kwh", 8.0, ASSUMPTION, "electricity, ₹ per kWh"),
       ("--pue", 1.6, ASSUMPTION, "district server-room overhead for cooling"),
       ("--rack-lakh-yr", 6.0, ASSUMPTION, "State Data Centre co-location per rack-year incl. power and "
                                           "cooling; may be nil for a Home Department tenant"),
       ("--district-link-lakh-yr", 3.0, ASSUMPTION, "one district backhaul link per year"),
       ("--core-links", 3, ASSUMPTION, "SDC uplink, DR uplink, SDC-DR replication link"),
       ("--core-link-lakh-yr", 20.0, ASSUMPTION, "one core link per year"),
       ("--core-fte", 10, ASSUMPTION, "platform team: lead 1, SRE/NOC on-call 4, backend 2, analytics 1, "
                                      "DBA 1, security 1"),
       ("--core-fte-lakh", 18.0, ASSUMPTION, "loaded cost per FTE-year"),
       ("--districts-per-engineer", 3, ASSUMPTION, "field engineers for edge hardware"),
       ("--field-fte-lakh", 8.0, ASSUMPTION, "loaded cost per field-engineer-year"),
       ("--dept-integration-lakh", 10.0, ASSUMPTION, "per department: ~2 person-months plus site visits"),
       ("--pilot-lakh", 30.0, ASSUMPTION, "wave 0 field costs; team time is in opex"),
       ("--hardening-fte-years", 3.0, ASSUMPTION, "PoC-to-production engineering, at the platform FTE rate"),
       ("--install-lakh", 0.5, ASSUMPTION, "per edge node: racking, cabling, OS hardening, commissioning"),
       ("--district-net-lakh", 10.0, ASSUMPTION, "per district: 10 GbE aggregation and fibre from camera "
                                                 "VLANs to the edge rack; the site survey replaces it"),
       ("--seats-per-room", 2, ASSUMPTION, "new operator workstations per control room"),
       ("--workstation-lakh", 1.5, ASSUMPTION, "one operator workstation"),
       ("--training-lakh", 2.0, ASSUMPTION, "per control room: operator and supervisor batches"),
       ("--audit-lakh", 25.0, ASSUMPTION, "STQC / CERT-In empanelled security audit before go-live"),
       ("--years", 5, ASSUMPTION, "total-cost-of-ownership horizon"))


def size(a) -> SimpleNamespace:
    s = SimpleNamespace()
    s.anpr = round(a.cameras * a.anpr_share)
    s.event = round(a.cameras * a.event_share)
    s.view = a.cameras - s.anpr - s.event
    s.anpr_nodes = math.ceil(s.anpr / a.node_anpr_streams)
    s.event_nodes = math.ceil(s.event / a.node_event_streams)
    s.nodes = math.ceil((s.anpr_nodes + s.event_nodes) * (1 + a.headroom))
    s.fps_a, s.fps_b = s.anpr * a.anpr_fps, s.event * a.event_fps

    s.sightings_day = s.anpr * a.vehicles_per_anpr_cam_day
    s.sightings_per_s = s.sightings_day / 86_400
    s.db_gb_day = s.sightings_day * a.sighting_row_bytes / 1e9
    s.crop_gb_day = s.sightings_day * a.crop_kb / 1e6
    s.count_rows_day = (s.anpr + s.event) * 86_400 / a.count_window_s   # tiers A and B both count
    s.count_gb_day = s.count_rows_day * a.count_row_bytes / 1e9

    # camera -> edge: tier A pulls the main stream, tier B the sub-stream, tier C nothing until watched
    s.tier_a_mbps = s.anpr * a.main_mbps
    s.tier_b_mbps = s.event * a.preview_mbps
    s.node_a_mbps = a.node_anpr_streams * a.main_mbps
    s.node_b_mbps = a.node_event_streams * a.preview_mbps

    # wire bytes taken as the stored row size; a worker's JSON per sighting is smaller (spool-row-bytes)
    s.meta_mbps = s.sightings_per_s * a.sighting_row_bytes * 8 / 1e6
    s.crop_mbps = s.sightings_per_s * a.crop_kb * 1e3 * 8 / 1e6
    s.count_mbps = s.count_rows_day / 86_400 * a.count_row_bytes * 8 / 1e6
    s.tile_mbps = (1 - a.fullres_share) * a.preview_mbps + a.fullres_share * a.main_mbps
    s.room_mbps = a.tiles_per_room * s.tile_mbps
    s.rooms = a.districts + a.state_rooms
    s.view_mbps = s.rooms * s.room_mbps
    # district rooms sit beside their edge; only the state room's wall crosses the backbone
    s.district_peak_mbps = (s.meta_mbps + s.crop_mbps + s.count_mbps) / a.districts + s.room_mbps
    s.wal_gb_day = (s.db_gb_day + s.count_gb_day) * a.wal_factor
    s.dr_mbps = s.wal_gb_day * 8e3 / 86_400

    # Model 4: every camera's main stream carried to, and recorded at, a central site
    s.m4_gbps = a.cameras * a.main_mbps / 1e3
    s.m4_pb = a.cameras * a.main_mbps * 86_400 / 8 / 1e9 * a.model4_days
    s.m4_floor_gbps = a.cameras * a.preview_mbps / 1e3
    s.m4_floor_pb = a.cameras * a.preview_mbps * 86_400 / 8 / 1e9 * a.model4_days

    s.sightings_tb = s.db_gb_day * a.hot_days / 1e3
    s.counts_tb = s.count_gb_day * a.hot_days / 1e3
    s.crops_tb = s.crop_gb_day * a.crop_days / 1e3
    s.hot_db_tb = s.sightings_tb + s.counts_tb
    s.archive_tb = (s.db_gb_day + s.count_gb_day) * 365 * a.archive_years / 1e3   # before compression
    s.backup_tb = a.backup_fulls * s.hot_db_tb + a.pitr_days * s.wal_gb_day / 1e3

    # one fully loaded edge node
    s.node_crop_gb = a.node_anpr_streams * a.vehicles_per_anpr_cam_day * a.crop_kb / 1e6 * a.crop_days
    counts_mb = 86_400 / a.count_window_s * a.spool_count_bytes / 1e6          # per camera per day
    spool_a = a.node_anpr_streams * (a.vehicles_per_anpr_cam_day * a.spool_row_bytes / 1e6 + counts_mb)
    spool_b = a.node_event_streams * counts_mb
    s.spool_mb_day = max(spool_a, spool_b)
    s.spool_days_now = a.spool_mb * 2**20 / 1e6 / s.spool_mb_day   # SPOOL_MAX_MB counts MiB (spool.py)
    s.spool_gb_target = s.spool_mb_day * a.spool_days / 1e3
    s.match_load = s.sightings_per_s * a.match_ms / 1e3   # busy connections at the average read rate
    return s


def core_bom(s) -> list[tuple[str, int, int, float, str]]:
    """(item, at the State Data Centre, at DR, unit ₹ lakh, spec). Prices are ASSUMPTIONS."""
    return [
        ("PostGIS database server", 2, 1, 24.0,
         f"2 × 32-core, 512 GB RAM, ~15 TB usable NVMe (RAID 10) for the {s.hot_db_tb:.1f} TB hot tier plus "
         "indexes, WAL and growth; primary and synchronous standby at SDC, asynchronous replica at DR"),
        ("Application server", 3, 2, 6.0,
         "1 × 32-core, 128 GB RAM; API, ingest, watchlist matching, SSO, secrets; stateless behind HAProxy"),
        ("Event bus broker (Kafka)", 3, 1, 6.0, "1 × 16-core, 64 GB RAM, 4 × 3.84 TB NVMe"),
        ("Object storage node (Ceph, S3 API)", 4, 0, 8.0,
         f"12 × 16 TB HDD; ~256 TB usable at 3 replicas, for the ≤ {s.archive_tb:.0f} TB warm archive "
         "and case evidence"),
        ("Backup repository", 0, 1, 16.0,
         f"pgBackRest target with object lock; the {s.backup_tb:.1f} TB of base backups and WAL, and "
         "audit-log exports"),
        ("Monitoring and logging server", 2, 1, 6.0, "Prometheus, Grafana, Loki; 1 × 16-core, 64 GB RAM, 8 TB"),
        ("Firewall (NGFW)", 2, 2, 8.0, "HA pair per site"),
        ("Core switch, 25 GbE", 2, 2, 4.0, "redundant pair per site"),
        ("Rack, PDUs, KVM, cabling", 3, 2, 2.0, "per rack; the rack count sets the hosting charge"),
    ]


def cost(a, s) -> SimpleNamespace:
    c = SimpleNamespace()
    c.bom = core_bom(s)
    c.core = sum((dc + dr) * unit for _, dc, dr, unit, _ in c.bom)
    c.edge = s.nodes * a.node_cost_lakh
    c.capex = c.edge + c.core
    c.racks = sum(dc + dr for item, dc, dr, _, _ in c.bom if item.startswith("Rack"))
    c.seats = s.rooms * a.seats_per_room
    c.field_fte = math.ceil(a.districts / a.districts_per_engineer)

    c.one_time = [   # (item, qty, unit ₹ lakh, basis)
        ("Department integration", a.departments, a.dept_integration_lakh,
         "adapters, credentials, firewall rules, registry import, per department"),
        ("Pilot district (wave 0)", 1, a.pilot_lakh,
         "field survey, ground-truth labelling for accuracy per camera class, travel"),
        ("Production hardening", a.hardening_fte_years, a.core_fte_lakh,
         "FTE-years: GPU-native decode, HA database, event bus, SSO, relay authorisation"),
        ("Edge installation and commissioning", s.nodes, a.install_lakh, "per node"),
        ("District network works", a.districts, a.district_net_lakh,
         "10 GbE aggregation and fibre from camera VLANs to the edge rack"),
        ("Control-room workstations", c.seats, a.workstation_lakh,
         f"{a.seats_per_room} per room where existing ones fall short of the spec"),
        ("Training", s.rooms, a.training_lakh, "per control room, incl. train-the-trainer"),
        ("Security audit before go-live", 1, a.audit_lakh, "STQC / CERT-In empanelled auditor"),
    ]
    c.one_time_total = sum(q * u for _, q, u, _ in c.one_time)

    kwh = s.nodes * a.node_kw * a.pue * 8_760
    c.opex = [   # (item, ₹ lakh a year, basis)
        ("Edge power", kwh * a.tariff_rs_kwh / 1e5,
         f"{s.nodes} nodes × {a.node_kw:g} kW × PUE {a.pue:g} × 8,760 h at ₹{a.tariff_rs_kwh:g}/kWh "
         f"= {kwh / 1e6:.2f} GWh"),
        ("State Data Centre hosting", c.racks * a.rack_lakh_yr, f"{c.racks} racks (SDC and DR), power included"),
        ("Platform team", a.core_fte * a.core_fte_lakh,
         f"{a.core_fte} FTE; control-room operators are existing police staff, not counted"),
        ("Field engineers", c.field_fte * a.field_fte_lakh, f"{c.field_fte}, one per {a.districts_per_engineer} districts"),
        ("District backhaul", a.districts * a.links_per_district * a.district_link_lakh_yr,
         f"{a.links_per_district} × {a.district_link_mbps} Mbps per district, two carriers"),
        ("Core links", a.core_links * a.core_link_lakh_yr, "SDC uplink, DR uplink, SDC-DR replication"),
        ("GPU refresh reserve", s.nodes * a.gpu_card_lakh / a.gpu_refresh_years,
         f"{s.nodes} GPUs × ₹{a.gpu_card_lakh:g} lakh every {a.gpu_refresh_years} years"),
        ("Software licences", 0.0, "open-source stack; optional vendor support not included"),
    ]
    c.opex_base = sum(v for _, v, _ in c.opex)
    c.amc = a.amc_pct / 100 * c.capex
    c.by_year = [c.opex_base + (c.amc if y > a.warranty_years else 0.0) for y in range(1, a.years + 1)]
    c.tco = c.capex + c.one_time_total + sum(c.by_year)
    c.per_cam_month = c.tco * 1e5 / (a.cameras * a.years * 12)
    c.per_analysed_month = c.tco * 1e5 / ((s.anpr + s.event) * a.years * 12)
    return c


def vary(a, **changes) -> tuple[SimpleNamespace, SimpleNamespace]:
    b = copy.copy(a)
    for k, v in changes.items():
        setattr(b, k, v)
    s = size(b)
    return s, cost(b, s)


def row(*cells):
    print("| " + " | ".join(str(c) for c in cells) + " |")


def head(*cells):
    row(*cells)
    row(*["---"] * len(cells))


def cr(lakh: float) -> str:
    return f"{lakh / 100:.1f}"


def rate(mbps: float) -> str:
    if mbps >= 10_000:
        return f"{mbps / 1e3:.1f} Gbps"
    if mbps >= 1_000:
        return f"{mbps / 1e3:.2f} Gbps"
    return f"{mbps:.0f} Mbps" if mbps >= 100 else f"{mbps:.1f} Mbps"


def print_hardware(a, s, c) -> None:
    print("### Edge node (quantity: see Edge compute)\n")
    head("Component", "Specification", "Basis")
    row("Form factor", "2U rack server, redundant power supplies", "ASSUMPTION")
    row("GPU", "1 × data-centre inference GPU with hardware video decode (NVDEC), 24 GB class, e.g. NVIDIA L4",
        "ASSUMPTION: the single-GPU node whose stream capacity the PoC measures first")
    row("CPU", "1 × 24-core server CPU", "ASSUMPTION: frames stay on the GPU; the CPU demuxes RTSP, batches OCR, does I/O")
    row("Memory", "128 GB", "ASSUMPTION")
    row("System disks", "2 × 960 GB SSD, RAID 1", "OS, containers, models")
    row("Data disks", "2 × 1.92 TB NVMe, RAID 1",
        f"{s.node_crop_gb:.0f} GB of crops per tier A node for {a.crop_days} d; spool {s.spool_gb_target:.1f} GB "
        f"for a {a.spool_days}-day outage")
    row("Network", "2 × 10 GbE (camera side, uplink) + 1 GbE management",
        f"ingest at capacity: {s.node_a_mbps:.0f} Mbps (tier A node), {s.node_b_mbps:.0f} Mbps (tier B node)")
    row("Load at capacity", f"tier A: {a.node_anpr_streams} streams, {a.node_anpr_streams * a.anpr_fps:.0f} frames/s; "
        f"tier B: {a.node_event_streams} streams, {a.node_event_streams * a.event_fps:.0f} frames/s",
        "ASSUMPTION until measured on the node")
    row("Power", f"~{a.node_kw:g} kW average", "ASSUMPTION; feeds the power line in opex")
    row("Price", f"₹{a.node_cost_lakh:.1f} lakh", "ASSUMPTION; GeM quote needed")
    print(f"\nStore-and-forward: a fully loaded node spools ~{s.spool_mb_day:.0f} MB a day of sightings and "
          f"counts; the PoC default cap (SPOOL_MAX_MB={a.spool_mb:.0f}) covers {s.spool_days_now:.1f} days, "
          f"{s.spool_gb_target:.1f} GB covers {a.spool_days}.\n")

    print("### Core: State Data Centre + DR site (the core capex line)\n")
    head("Item", "SDC", "DR", "Unit (₹ lakh)", "Total (₹ lakh)", "Specification")
    for item, dc, dr, unit, spec in c.bom:
        row(item, dc, dr, f"{unit:.1f}", f"{(dc + dr) * unit:.1f}", spec)
    row("**Core DC + DR**", "", "", "", f"**{c.core:.1f}**", f"= ₹{cr(c.core)} crore")

    print("\n### Control-room workstation\n")
    head("Item", "Specification", "Basis", "Qty", "Unit (₹ lakh)")
    row("Operator workstation",
        "8-core desktop CPU, 32 GB RAM, discrete GPU with H.264/H.265 hardware decode, 2 × 27-inch displays, "
        "1 GbE, current Chrome or Edge",
        f"decodes one {a.tiles_per_room}-tile wall, {s.room_mbps:.1f} Mbps with {a.fullres_share:.0%} of tiles at "
        "full resolution; the GPU decodes so the CPU stays free",
        c.seats, f"{a.workstation_lakh:.1f}")


def print_network(a, s) -> None:
    print("### Camera → edge (inside the district network)\n")
    head("Leg", "Cameras", "Per camera", "Average district", "Statewide")
    row("Tier A: main stream, continuous", f"{s.anpr:,}", f"{a.main_mbps:g} Mbps",
        rate(s.tier_a_mbps / a.districts), rate(s.tier_a_mbps))
    row("Tier B: sub-stream, continuous", f"{s.event:,}", f"{a.preview_mbps:g} Mbps",
        rate(s.tier_b_mbps / a.districts), rate(s.tier_b_mbps))
    row("Tier C: only while watched", f"{s.view:,}", "0 when idle",
        f"≤ {rate(s.room_mbps)} (one {a.tiles_per_room}-tile wall)", f"≤ {rate(s.view_mbps)} (every wall)")
    row("**Continuous total**", f"{s.anpr + s.event:,}", "",
        f"**{rate((s.tier_a_mbps + s.tier_b_mbps) / a.districts)}**", f"**{rate(s.tier_a_mbps + s.tier_b_mbps)}**")

    print("\n### Edge → core and viewing\n")
    head("Flow", "Rate", "Note")
    row("Edge → core: metadata", f"{s.meta_mbps:.1f} Mbps", f"average; {s.sightings_per_s:,.0f} sightings/s")
    row("Edge → core: plate crops", f"{s.crop_mbps:.0f} Mbps", "or keep crops at edge, pull on alert/search (→ ~0)")
    row("Edge → core: vehicle/person counts", f"{s.count_mbps:.1f} Mbps",
        f"{s.count_rows_day / 86_400:,.0f} rows/s: one per analysed camera per {a.count_window_s} s")
    row("Control-room viewing", f"{s.view_mbps:.0f} Mbps",
        f"peak; {s.rooms * a.tiles_per_room} tiles, {a.fullres_share:.0%} at full resolution; district rooms "
        f"sit beside their edge, so only the state room's wall ({s.room_mbps:.1f} Mbps) crosses the backbone")
    row("SDC → DR: database replication", f"{s.dr_mbps:.1f} Mbps",
        f"average WAL, {s.wal_gb_day:.0f} GB a day at {a.wal_factor:g}× the stored bytes")
    row("Backhaul per district, peak", f"{s.district_peak_mbps:.1f} Mbps",
        f"its share of metadata, crops and counts, plus the state room watching {a.tiles_per_room} of its cameras; "
        f"links: {a.links_per_district} × {a.district_link_mbps} Mbps "
        f"({a.links_per_district * a.district_link_mbps / s.district_peak_mbps:.1f}× headroom)")

    print("\n### Model 4 counterfactual: carry and record every stream centrally\n")
    head("", "Model 4 (central VMS)", "This design")
    row("Backbone, sustained", f"{s.m4_gbps:,.0f} Gbps ({a.cameras:,} × {a.main_mbps:g} Mbps)",
        f"{s.meta_mbps:.1f} Mbps metadata; {s.meta_mbps + s.crop_mbps + s.count_mbps:.1f} Mbps with crops and counts")
    row(f"Recording, {a.model4_days} days", f"{s.m4_pb:.1f} PB; {2 * s.m4_pb:.1f} PB with a DR copy",
        f"none: video stays on department NVRs; {s.hot_db_tb + s.crops_tb:.1f} TB of sightings, counts and crops")
    row(f"Floor: record only the {a.preview_mbps:g} Mbps sub-stream", f"{s.m4_floor_gbps:,.0f} Gbps; "
        f"{s.m4_floor_pb:.1f} PB ({2 * s.m4_floor_pb:.1f} PB with DR)", "")


def print_storage(a, s) -> None:
    print("### Storage\n")
    head("Data", "Per day", "Retention", "Total")
    row("Video", "—", "stays on department NVR/VMS (7–15+ days)", "not duplicated")
    row("Sightings (Postgres, partitioned)", f"{s.sightings_day / 1e6:.0f} M rows / {s.db_gb_day:.0f} GB",
        f"{a.hot_days} d hot", f"{s.sightings_tb:.1f} TB")
    row("Plate crops (object store at edge)", f"{s.crop_gb_day:.0f} GB", f"{a.crop_days} d", f"{s.crops_tb:.1f} TB")
    row("Vehicle/person counts (Postgres, partitioned)", f"{s.count_rows_day / 1e6:.0f} M rows / {s.count_gb_day:.0f} GB",
        f"{a.hot_days} d hot", f"{s.counts_tb:.1f} TB")
    row("Warm archive (Parquet on the core object store)", "—", f"{a.archive_years} years",
        f"≤ {s.archive_tb:.0f} TB (upper bound: database bytes, before compression)")
    row("Backups (base backups + WAL, at DR)", f"{s.wal_gb_day:.0f} GB WAL",
        f"{a.backup_fulls} weekly fulls, {a.pitr_days} d point-in-time", f"{s.backup_tb:.1f} TB")
    row("Edge spool (store-and-forward)", f"~{s.spool_mb_day:.0f} MB per node", "until replayed",
        f"{s.spool_gb_target:.1f} GB per node for {a.spool_days} d")
    row("Alert evidence", "small", "per case / legal hold", "cold archive")
    row("Audit log", "small", "legal retention", "WORM export (object lock)")


def print_compute(a, s, c) -> None:
    print("### Analytics tiers\n")
    head("Tier", "Share", "Cameras", "Analysis", "Continuous compute")
    row("A — ANPR", f"{a.anpr_share:.0%}", f"{s.anpr:,}", f"{a.anpr_fps:g} fps, full decode", "yes")
    row("B — event analytics", f"{a.event_share:.0%}", f"{s.event:,}", f"{a.event_fps:g} fps, keyframe-only decode",
        "yes (light)")
    row("C — view & record", f"{1 - a.anpr_share - a.event_share:.0%}", f"{s.view:,}",
        "none; relayed only while watched", "no")
    print(f"\nInference load: **{s.fps_a + s.fps_b:,.0f} frames/s** statewide "
          f"(tier A {s.fps_a:,.0f}, tier B {s.fps_b:,.0f}).\n")

    print("### Edge compute\n")
    head("Item", "Value", "Basis")
    row("Tier A nodes", s.anpr_nodes, f"{s.anpr:,} / {a.node_anpr_streams} streams per node (ASSUMPTION)")
    row("Tier B nodes", s.event_nodes, f"{s.event:,} / {a.node_event_streams} streams per node (ASSUMPTION)")
    row("Headroom", f"{a.headroom:.0%}", "N+1 failover and growth")
    row("**Edge GPU nodes**", f"**{s.nodes}**",
        f"≈ {s.nodes / a.districts:.1f} per district, co-located with district control rooms")
    row("GPUs at the core", 0, "the core matches, searches and stores; it runs no inference")
    row("Watchlist matching at the core", f"{s.match_load:.2f} busy connections",
        f"{s.sightings_per_s:,.0f} reads/s × {a.match_ms:g} ms median (MEASURED at 100,000 entries)")

    print("\n### Sensitivity: the two levers\n")
    head("Case", "Edge nodes", "Capex (₹ crore)", f"{a.years}-year TCO (₹ crore)", "₹ per camera per month")
    cases = [("As planned", {})]
    cases += [(f"{n} tier A streams per node", {"node_anpr_streams": n}) for n in (30, 45, 90)]
    cases += [(f"Tier A share {x:.0%}", {"anpr_share": x}) for x in (0.05, 0.15)]
    for label, changes in cases:
        vs, vc = vary(a, **changes)
        row(label, vs.nodes, cr(vc.capex), cr(vc.tco), f"{vc.per_cam_month:.0f}")
    vs, vc = vary(a, anpr_share=a.anpr_share + 0.01)
    print(f"\nEach 1% of cameras moved from tier C into tier A adds {vs.nodes - s.nodes} nodes "
          f"(₹{cr(vc.capex - c.capex)} crore capex, ₹{cr(vc.tco - c.tco)} crore over {a.years} years).")


def print_costs(a, s, c) -> None:
    print("### Indicative capital cost (ASSUMPTIONS — replace with GeM quotes)\n")
    head("Item", "Qty", "Unit (₹ lakh)", "Total (₹ crore)")
    row("Edge GPU nodes", s.nodes, f"{a.node_cost_lakh:.1f}", cr(c.edge))
    row("Core DC + DR", 1, f"{c.core:.1f}", cr(c.core))
    row("**Total**", "", "", f"**{cr(c.capex)}**")

    print("\n### One-time implementation (ASSUMPTIONS)\n")
    head("Item", "Qty", "Unit (₹ lakh)", "Total (₹ crore)", "Basis")
    for item, qty, unit, basis in c.one_time:
        row(item, f"{qty:g}", f"{unit:.1f}", f"{qty * unit / 100:.2f}", basis)
    row("**Total**", "", "", f"**{c.one_time_total / 100:.2f}**", "")

    print("\n### Annual operating cost (ASSUMPTIONS)\n")
    head("Item", "₹ crore a year", "Basis")
    for item, lakh, basis in c.opex:
        row(item, f"{lakh / 100:.2f}", basis)
    row(f"**Years 1–{a.warranty_years}**", f"**{c.opex_base / 100:.2f}**", "hardware under warranty")
    row(f"AMC from year {a.warranty_years + 1}", f"{c.amc / 100:.2f}", f"{a.amc_pct:g}% of ₹{cr(c.capex)} crore capex")
    row(f"**Years {a.warranty_years + 1}–{a.years}**", f"**{(c.opex_base + c.amc) / 100:.2f}**", "")

    print(f"\n### {a.years}-year total cost of ownership\n")
    head("Component", "₹ crore")
    row("Hardware capex", cr(c.capex))
    row("One-time implementation", f"{c.one_time_total / 100:.1f}")
    row(f"Operating cost, years 1–{a.years}", f"{sum(c.by_year) / 100:.1f}")
    row(f"**{a.years}-year TCO**", f"**{cr(c.tco)}**")
    row("Per camera per month", f"₹{c.per_cam_month:.0f} (all {a.cameras:,} cameras)")
    row("Per analysed camera per month", f"₹{c.per_analysed_month:.0f} ({s.anpr + s.event:,} tier A + B cameras)")


def print_inputs(a) -> None:
    print("### Inputs\n")
    head("Input", "Value", "Kind", "Basis")
    group = None
    for g, flag, kind, basis in INPUTS:
        if g != group:
            row(f"**{g}**", "", "", "")
            group = g
        value = getattr(a, flag[2:].replace("-", "_"))
        row(f"`{flag}`", f"{value:,}" if isinstance(value, int) else f"{value:g}", kind, basis)


def main() -> None:
    a = p.parse_args()
    s = size(a)
    c = cost(a, s)
    for section in (lambda: print_hardware(a, s, c), lambda: print_network(a, s), lambda: print_storage(a, s),
                    lambda: print_compute(a, s, c), lambda: print_costs(a, s, c), lambda: print_inputs(a)):
        section()
        print()


if __name__ == "__main__":
    main()
