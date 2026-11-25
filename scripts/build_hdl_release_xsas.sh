#!/bin/bash
# Build XSAs for HDL designs a Kuiper release ships no XSA for.
#
# The coverage gate (test/xsa/test_hdl_release_coverage.py) only needs the
# hardware handoff, which Vivado can export as soon as the block design is
# generated.  This runs each project with ADI_SKIP_SYNTHESIS so a design takes
# minutes instead of the hours a bitstream does.  The XSAs carry no bitstream.
#
# Usage:
#   source <Vivado>/settings64.sh
#   scripts/build_hdl_release_xsas.sh <hdl checkout> <out dir> [project/carrier ...]
#
# Without designs, every "local_xsa" entry of the release inventory is built.
# Results land in <out dir>/<project>_<carrier>/system_top.xsa; point
# ADI_XSA_LOCAL_DIR at <out dir> to run the gate on them.  Finished designs
# are skipped, so the script can be rerun.
set -u
hdl=$(realpath "${1:?HDL checkout}")
out=$(mkdir -p "${2:?output directory}" && realpath "$2")
shift 2
here=$(dirname "$(realpath "$0")")
if [ $# -eq 0 ]; then
  inventory=$here/../adidt/xsa/config/hdl_2026_r1_designs.json
  mapfile -t designs < <(python3 - "$inventory" <<'PY'
import json, sys
for d in json.load(open(sys.argv[1]))["designs"]:
    if d["local_xsa"]:
        print(f"{d['project']}/{d['carrier']}")
PY
  )
else
  designs=("$@")
fi

tcl=$out/xsa_only.tcl
cat > "$tcl" <<'TCL'
set ::env(ADI_SKIP_SYNTHESIS) 1
source system_project.tcl
set name [get_property NAME [current_project]]
file mkdir $name.sdk
write_hw_platform -fixed -force -file $name.sdk/system_top.xsa
TCL

git -C "$hdl" rev-parse HEAD > "$out/HDL_REV"
failed=0
for design in "${designs[@]}"; do
  tag=${design//\//_}
  if [ -s "$out/$tag/system_top.xsa" ]; then
    echo "SKIP $design"
    continue
  fi
  mkdir -p "$out/$tag"
  if ! cd "$hdl/projects/$design"; then
    echo "FAIL $design (no such project)"
    failed=1
    continue
  fi
  start=$(date +%s)
  if ! make lib > "$out/$tag/lib.log" 2>&1; then
    echo "FAIL $design (libraries, see $out/$tag/lib.log)"
    failed=1
    continue
  fi
  vivado -mode batch -source "$tcl" -log "$out/$tag/vivado.log" \
    -journal "$out/$tag/vivado.jou" > /dev/null 2>&1
  xsa=$(ls ./*.sdk/system_top.xsa 2> /dev/null | head -1)
  if [ -n "$xsa" ]; then
    cp "$xsa" "$out/$tag/system_top.xsa"
    echo "OK $design $(($(date +%s) - start))s"
  else
    echo "FAIL $design (vivado, see $out/$tag/vivado.log)"
    failed=1
  fi
done
exit $failed
