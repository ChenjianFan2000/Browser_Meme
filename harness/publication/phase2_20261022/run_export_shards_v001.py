"""Run unchanged export_evidence.py in independent, bounded Python processes.

Only a pending/blocked aggregate is produced. No approval, packing or upload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

import package as common


def load_bound(path):
    with common.safe_open(path) as stream:
        data=stream.read()
    return json.loads(data),hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def run_shards(source_root,inventory_path,output_dir,*,shards=8,jobs=8,inventory_sha256=None,exporter=None):
    if not 1<=shards<=8 or not 1<=jobs<=8:
        raise ValueError("shards/jobs must be between 1 and 8")
    root=common.no_links(source_root).resolve(strict=True)
    inventory_path=common.no_links(inventory_path).resolve(strict=True)
    parent,parent_sha=load_bound(inventory_path)
    if inventory_sha256 is not None and common.checked_sha(inventory_sha256)!=parent_sha:
        raise ValueError("parent inventory differs from pinned SHA256")
    if parent.get("schema_version")!=1 or parent.get("status")!="inventory_only_not_publication_approval":
        raise ValueError("expected schema_version=1 unapproved inventory")
    if Path(parent.get("source_root",str(root))).resolve()!=root:
        raise ValueError("inventory source root differs from explicit source root")
    rows=parent.get("entries")
    if not isinstance(rows,list) or not rows: raise ValueError("nonempty inventory entries required")
    for row in rows:
        if not isinstance(row,dict): raise ValueError("inventory row must be an object")
        common.relative_name(row.get("source_path"),protected=False)
        common.relative_name(row.get("archive_path"),protected=False)
        if "restore_path" in row: common.relative_name(row["restore_path"],protected=False)
        if "expected_original_sha256" in row: common.checked_sha(row["expected_original_sha256"])
    common.check_unique(row["archive_path"] for row in rows)
    common.check_unique(row["source_path"] for row in rows)
    excluded_roots=parent.get("excluded_roots",[])
    if not isinstance(excluded_roots,list): raise ValueError("excluded_roots must be a list")
    excluded_keys=set()
    source_keys={row["source_path"].casefold() for row in rows}
    for excluded in excluded_roots:
        path=common.relative_name(excluded.get("source_path"),protected=False)
        if excluded.get("content_read_or_hashed") is not False:
            raise ValueError("parent exclusion must explicitly be unread/unhashed")
        if path.casefold() in excluded_keys or path.casefold() in source_keys:
            raise ValueError("duplicate or overlapping exact parent exclusion")
        excluded_keys.add(path.casefold())
    rows=sorted(rows,key=lambda row:row["archive_path"])
    source_to_archive={row["source_path"]:row["archive_path"] for row in rows}
    output=common.no_links(output_dir)
    if not output.is_relative_to(root): raise ValueError("output must be inside explicit source root")
    if output.exists(): raise ValueError("output directory must be new and exclusive")
    if any(root.joinpath(*r["source_path"].split("/")).is_relative_to(output) for r in rows):
        raise ValueError("output overlaps inventoried sources")
    exporter=common.no_links(exporter or Path(__file__).with_name("export_evidence.py")).resolve(strict=True)
    exporter_sha=common.digest_file(exporter)
    count=min(shards,len(rows)); groups=[rows[n::count] for n in range(count)]
    output.mkdir(parents=True,exist_ok=False)
    records=[]
    for n,group in enumerate(groups,1):
        shard_id=f"shard-{n:03d}"
        path=output/(shard_id+".inventory.json")
        child={"schema_version":1,"status":"inventory_only_not_publication_approval","created_at_utc":now(),
               "source_root":str(root),"entries":group,"excluded_roots":[],
               "parent_inventory_sha256":parent_sha,"shard_id":shard_id,"shard_count":count}
        common.write_json_new(path,child)
        records.append({"shard_id":shard_id,"entry_count":len(group),"inventory_path":path.relative_to(root).as_posix(),
                        "inventory_sha256":common.digest_file(path),"output_dir":(output/shard_id).relative_to(root).as_posix(),
                        "stdout_path":(output/(shard_id+".stdout.txt")).relative_to(root).as_posix(),
                        "stderr_path":(output/(shard_id+".stderr.txt")).relative_to(root).as_posix()})
    plan={"schema_version":1,"kind":"independent_export_process_shards_v001","status":"planned_not_approved",
          "created_at_utc":now(),"parent_inventory_path":inventory_path.relative_to(root).as_posix(),
          "parent_inventory_sha256":parent_sha,"scheduler_sha256":common.digest_file(__file__),
          "exporter_sha256":exporter_sha,"requested_shards":shards,"actual_shards":count,"max_processes":jobs,
          "child_workers":1,"assignment":"archive_path_sorted_round_robin","input_entries":len(rows),"shards":records}
    common.write_json_new(output/"shard-plan.json",plan)
    started=time.monotonic(); last_progress=started; next_index=0; active={}; scheduler_error=None
    print(json.dumps({"sharded_export_started":True,"input_entries":len(rows),"shards":count,"max_processes":jobs}),flush=True)
    try:
        while next_index<count or active:
            while next_index<count and len(active)<jobs:
                record=records[next_index]
                stdout=(root/record["stdout_path"]).open("xb")
                stderr=(root/record["stderr_path"]).open("xb")
                argv=[sys.executable,str(exporter),"export","--source-root",str(root),"--inventory",
                      str(root/record["inventory_path"]),"--output-dir",str(root/record["output_dir"]),"--workers","1"]
                try:
                    process=subprocess.Popen(argv,cwd=root,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                                             creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                except BaseException:
                    stdout.close(); stderr.close(); raise
                record.update(pid=process.pid,parent_pid=os.getpid(),started_at_utc=now())
                active[next_index]=(process,stdout,stderr); next_index+=1
                common.write_json_new(output/(record["shard_id"]+".launch.json"),
                                      {"pid":process.pid,"parent_pid":os.getpid(),"argv":argv,"started_at_utc":record["started_at_utc"],
                                       "inventory_sha256":record["inventory_sha256"],"exporter_sha256":exporter_sha})
            for n,(process,stdout,stderr) in list(active.items()):
                code=process.poll()
                if code is None: continue
                stdout.close(); stderr.close()
                records[n].update(exit_code=code,finished_at_utc=now())
                del active[n]
            current=time.monotonic()
            if current-last_progress>=15:
                print(json.dumps({"completed_shards":sum("exit_code" in r for r in records),"active_processes":len(active),
                                  "started_shards":next_index,"elapsed_seconds":round(current-started,1)}),flush=True)
                last_progress=current
            if active: time.sleep(0.1)
    except BaseException as error:
        scheduler_error=type(error).__name__
        for n,(process,stdout,stderr) in list(active.items()):
            if process.poll() is None: process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            stdout.close(); stderr.close()
            records[n].update(exit_code=process.returncode,finished_at_utc=now(),scheduler_interrupted=True)
        active.clear()
    entries=[]; exclusions=list(parent.get("excluded_roots",[])); failures=[]; shard_failures=[]; seen=set()
    for n,record in enumerate(records):
        record["stdout_sha256"]=common.digest_file(root/record["stdout_path"]) if (root/record["stdout_path"]).exists() else None
        record["stderr_sha256"]=common.digest_file(root/record["stderr_path"]) if (root/record["stderr_path"]).exists() else None
        expected={r["source_path"]:r for r in groups[n]}
        manifest_path=root/record["output_dir"]/"export-manifest.pending.json"
        local_seen=set()
        try:
            child,child_sha=load_bound(manifest_path)
            record.update(manifest_path=manifest_path.relative_to(root).as_posix(),manifest_sha256=child_sha,status=child.get("status"))
            if child.get("schema_version")!=1 or child.get("status") not in {"exported_pending_independent_approval","export_blocked"}:
                raise ValueError("child manifest has invalid/nonpending status")
            if child.get("inventory_sha256")!=record["inventory_sha256"] or child.get("generator_sha256")!=exporter_sha:
                raise ValueError("child manifest inventory/exporter SHA binding mismatch")
            accepted={"entry":[],"excluded":[],"failure":[]}
            for kind,key in [("entry","entries"),("excluded","exclusions"),("failure","failures")]:
                values=child.get(key)
                if not isinstance(values,list): raise ValueError("child result list missing")
                for row in values:
                    if not isinstance(row,dict): raise ValueError("child result must be an object")
                    source=row.get("original_source_path") if kind=="entry" else row.get("source_path")
                    if source not in expected or source in local_seen: raise ValueError("unexpected/duplicate child source")
                    archive=expected[source]["archive_path"]
                    if kind!="failure" and row.get("archive_path")!=archive: raise ValueError("child archive mapping mismatch")
                    if kind=="entry":
                        common.relative_name(row.get("source_path"))
                        common.checked_sha(row.get("original_sha256")); common.checked_sha(row.get("export_sha256"))
                        if row.get("treatment") not in {"unchanged","redacted"}: raise ValueError("child treatment invalid")
                        if row["treatment"]=="unchanged" and (row["source_path"]!=source or row["original_sha256"]!=row["export_sha256"]):
                            raise ValueError("unchanged child source/hash mismatch")
                        if row["treatment"]=="redacted" and not root.joinpath(*row["source_path"].split("/")).is_relative_to(root/record["output_dir"]):
                            raise ValueError("redacted child source escapes its output")
                        if "expected_original_sha256" in expected[source] and row["original_sha256"]!=expected[source]["expected_original_sha256"]:
                            raise ValueError("child original hash differs from inventory")
                    if kind=="excluded" and row.get("content_read_or_hashed") is not False:
                        raise ValueError("child exclusion is not explicitly unread/unhashed")
                    local_seen.add(source); accepted[kind].append(row)
            if set(expected)!=local_seen: raise ValueError("child result coverage incomplete")
            if child.get("counts")!={"included":len(accepted["entry"]),"excluded":len(accepted["excluded"]),
                                    "redacted":sum(e["treatment"]=="redacted" for e in accepted["entry"])}:
                raise ValueError("child result counts mismatch")
            entries.extend(accepted["entry"]); exclusions.extend(accepted["excluded"]); failures.extend(accepted["failure"])
            seen.update(local_seen)
            if record.get("exit_code")!=0 or child["status"]=="export_blocked":
                shard_failures.append({"shard_id":record["shard_id"],"reason":"child_nonzero_exit_or_blocked","exit_code":record.get("exit_code")})
        except Exception as error:
            local_seen=set()
            shard_failures.append({"shard_id":record["shard_id"],"reason":"missing_or_invalid_child_result","error_type":type(error).__name__,"exit_code":record.get("exit_code")})
            for source,row in expected.items():
                failures.append({"source_path":source,"archive_path":row["archive_path"],"error_type":"ShardExecutionFailure",
                                 "reason":"missing or invalid independently recorded child result","shard_id":record["shard_id"]})
                seen.add(source)
    if seen!=set(source_to_archive): raise ValueError("aggregate source coverage invariant failed")
    common.check_unique(e["archive_path"] for e in entries)
    if common.digest_file(inventory_path)!=parent_sha: scheduler_error="ParentInventoryChanged"
    value={"schema_version":1,"status":"export_blocked" if failures or shard_failures or scheduler_error else "exported_pending_independent_approval",
           "created_at_utc":now(),"inventory_sha256":parent_sha,"generator_sha256":exporter_sha,
           "scheduler_sha256":common.digest_file(__file__),"shard_plan_sha256":common.digest_file(output/"shard-plan.json"),
           "source_root":str(root),"entries":sorted(entries,key=lambda x:x["archive_path"]),
           "exclusions":sorted(exclusions,key=lambda x:x["source_path"]),"failures":sorted(failures,key=lambda x:x["source_path"]),
           "counts":{"included":len(entries),"excluded":len(exclusions),"redacted":sum(e["treatment"]=="redacted" for e in entries)},
           "coverage":{"inventory_entry_count":len(rows),"included_entry_count":len(entries),
                       "excluded_entry_count":len(exclusions)-len(parent.get("excluded_roots",[])),"failure_entry_count":len(failures),
                       "parent_excluded_root_count":len(parent.get("excluded_roots",[])),"all_original_entries_accounted_for":True},
           "shards":records,"shard_failures":shard_failures,"scheduler_error":scheduler_error,
           "originals_modified":False,"secret_values_in_logs":False,"not_yet_approved_for_publication":True,
           "actual_process_count":count,"max_concurrent_processes":jobs,"child_workers":1}
    if value["coverage"]["included_entry_count"]+value["coverage"]["excluded_entry_count"]+len(failures)!=len(rows):
        raise ValueError("aggregate coverage denominator mismatch")
    common.write_json_new(output/"export-manifest.pending.json",value)
    common.write_json_new(output/"shard-execution.json",{"schema_version":1,"status":value["status"],"scheduler_error":scheduler_error,
                          "parent_inventory_sha256":parent_sha,"shards":records,"shard_failures":shard_failures})
    print(json.dumps({"status":value["status"],"counts":value["counts"],"failure_entries":len(failures),"shard_failures":len(shard_failures)}),flush=True)
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",required=True,type=Path)
    parser.add_argument("--inventory",required=True,type=Path)
    parser.add_argument("--inventory-sha256")
    parser.add_argument("--output-dir",required=True,type=Path)
    parser.add_argument("--shards",type=int,choices=range(1,9),default=8)
    parser.add_argument("--jobs",type=int,choices=range(1,9),default=8)
    args=parser.parse_args()
    try:
        value=run_shards(args.source_root,args.inventory,args.output_dir,shards=args.shards,jobs=args.jobs,inventory_sha256=args.inventory_sha256)
        return 0 if value["status"]=="exported_pending_independent_approval" else 2
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(json.dumps({"status":"export_blocked","error_type":type(error).__name__}),file=sys.stderr)
        return 2


if __name__=="__main__": raise SystemExit(main())
