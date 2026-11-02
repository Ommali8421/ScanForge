#!/usr/bin/env python3
"""
Stress Test Harness: Frontend UI/UX Redesign, Component Edge Cases & API Contract Conformance
Milestone M2 Empirical Verification
"""

import sys
import json
import urllib.request
import urllib.error
import re
from pathlib import Path

BASE_URL = "http://localhost:3000/api"
FRONTEND_SRC = Path("/home/om_mali/scanforge/frontend/src")

def log(msg, status="INFO"):
    colors = {
        "INFO": "\033[94m[INFO]\033[0m",
        "PASS": "\033[92m[PASS]\033[0m",
        "FAIL": "\033[91m[FAIL]\033[0m",
        "WARN": "\033[93m[WARN]\033[0m",
    }
    print(f"{colors.get(status, status)} {msg}")

def test_api_health():
    log("Testing GET /api/health...")
    req = urllib.request.Request(f"{BASE_URL}/health")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        data = json.loads(resp.read().decode())
        assert "status" in data and data["status"] == "ok"
        assert "engine" in data
        assert "db" in data and data["db"] == "connected"
        assert "redis" in data and data["redis"] == "connected"
        assert "disk_free_gb" in data and isinstance(data["disk_free_gb"], (int, float))
        assert "version" in data
    log("GET /api/health conforms to contract.", "PASS")
    return data

def test_api_capabilities():
    log("Testing GET /api/capabilities...")
    req = urllib.request.Request(f"{BASE_URL}/capabilities")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        data = json.loads(resp.read().decode())
        assert "engine" in data
        assert "gpu_available" in data and isinstance(data["gpu_available"], bool)
        assert "scan_types" in data and set(["photo", "gaussian_splat", "lidar"]).issubset(set(data["scan_types"]))
        assert "lidar_enabled" in data and isinstance(data["lidar_enabled"], bool)
        assert "quality_presets" in data and set(["draft", "standard", "high"]).issubset(set(data["quality_presets"]))
        assert "mesh_routes" in data and set(["auto", "photogrammetry", "depth_fusion"]).issubset(set(data["mesh_routes"]))
        assert "format_matrix" in data and isinstance(data["format_matrix"], dict)
        assert "photo" in data["format_matrix"]
        assert "gaussian_splat" in data["format_matrix"]
        assert "lidar" in data["format_matrix"]
        assert "limits" in data
        assert "max_upload_mb" in data["limits"]
        assert "max_video_seconds" in data["limits"]
    log("GET /api/capabilities conforms to contract.", "PASS")
    return data

def test_api_jobs_pagination_and_filters():
    log("Testing GET /api/jobs pagination and filters...")
    # Test valid pagination
    req = urllib.request.Request(f"{BASE_URL}/jobs?limit=5&offset=0")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert "total" in data and isinstance(data["total"], int)
        assert "items" in data and isinstance(data["items"], list)

    # Test limit boundary: limit=0 (should fail 422)
    try:
        urllib.request.urlopen(f"{BASE_URL}/jobs?limit=0")
        assert False, "limit=0 should fail 422"
    except urllib.error.HTTPError as e:
        assert e.code == 422, f"Expected 422, got {e.code}"
    log("GET /api/jobs limit=0 correctly rejected with 422.", "PASS")

    # Test limit boundary: limit=101 (should fail 422)
    try:
        urllib.request.urlopen(f"{BASE_URL}/jobs?limit=101")
        assert False, "limit=101 should fail 422"
    except urllib.error.HTTPError as e:
        assert e.code == 422, f"Expected 422, got {e.code}"
    log("GET /api/jobs limit=101 correctly rejected with 422.", "PASS")

    # Test unknown status filter
    req = urllib.request.Request(f"{BASE_URL}/jobs?status=nonexistent_status")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["total"] == 0
        assert len(data["items"]) == 0
    log("GET /api/jobs with unknown status returns empty list cleanly.", "PASS")

def test_api_calibrate_edge_cases():
    log("Testing POST /api/jobs/{id}/calibrate edge cases...")
    # Query an existing completed job if available, or use dummy
    req = urllib.request.Request(f"{BASE_URL}/jobs?limit=10")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        completed_job = next((j for j in data["items"] if j["status"] == "completed"), None)

    job_id = completed_job["id"] if completed_job else "00000000-0000-0000-0000-000000000000"

    # Test 1: Negative real_distance
    payload = json.dumps({
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [1.0, 1.0, 1.0],
        "real_distance": -2.5
    }).encode()
    req = urllib.request.Request(f"{BASE_URL}/jobs/{job_id}/calibrate", data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
        assert False, "Negative distance should fail validation"
    except urllib.error.HTTPError as e:
        assert e.code in (400, 422), f"Expected 400 or 422, got {e.code}"
        err_body = e.read().decode()
        log(f"Negative distance rejected with HTTP {e.code}: {err_body[:100]}", "PASS")

    # Test 2: Zero real_distance
    payload = json.dumps({
        "point_a": [0.0, 0.0, 0.0],
        "point_b": [1.0, 1.0, 1.0],
        "real_distance": 0.0
    }).encode()
    req = urllib.request.Request(f"{BASE_URL}/jobs/{job_id}/calibrate", data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
        assert False, "Zero distance should fail validation"
    except urllib.error.HTTPError as e:
        assert e.code in (400, 422), f"Expected 400 or 422, got {e.code}"
        err_body = e.read().decode()
        log(f"Zero distance rejected with HTTP {e.code}: {err_body[:100]}", "PASS")

    # Test 3: Identical points (distance <= 1e-6) on completed job
    if completed_job:
        payload = json.dumps({
            "point_a": [1.0, 2.0, 3.0],
            "point_b": [1.0, 2.0, 3.0],
            "real_distance": 2.0
        }).encode()
        req = urllib.request.Request(f"{BASE_URL}/jobs/{job_id}/calibrate", data=payload, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            assert False, "Identical points should fail"
        except urllib.error.HTTPError as e:
            assert e.code == 400, f"Expected 400, got {e.code}"
            err_body = json.loads(e.read().decode())
            assert "detail" in err_body
            assert "close together" in err_body["detail"].lower()
            log(f"Identical points rejected with HTTP 400: '{err_body['detail']}'", "PASS")
    else:
        log("No completed job in DB to test identical points calibrate execution; tested validation.", "WARN")

def test_user_guide_modal_code():
    log("Stress-testing UserGuideModal.tsx...")
    modal_file = FRONTEND_SRC / "components" / "UserGuideModal.tsx"
    content = modal_file.read_text()

    # Verify 5 tabs
    tabs_match = re.search(r"tabs\s*=\s*\[(.*?)\];", content, re.DOTALL)
    assert tabs_match, "tabs array not found in UserGuideModal.tsx"
    tabs_block = tabs_match.group(1)
    tab_ids = re.findall(r"id:\s*(\d+)", tabs_block)
    assert len(tab_ids) == 5, f"Expected 5 tabs, found {len(tab_ids)}: {tab_ids}"
    log(f"UserGuideModal has all 5 tabs defined: {tab_ids}", "PASS")

    # Verify each tab content section exists
    for tab_num in range(1, 6):
        assert f"activeGuideTab === {tab_num}" in content, f"Tab {tab_num} content block missing"
    log("All 5 tab content rendering blocks verified.", "PASS")

    # DEFECT CHECK: Keyboard Escape handler
    has_escape_listener = "Escape" in content or "keydown" in content or "keyup" in content
    if not has_escape_listener:
        log("DEFECT CONFIRMED: UserGuideModal does NOT implement 'Escape' keyboard event listener!", "FAIL")
    else:
        log("UserGuideModal implements Escape keyboard listener.", "PASS")

    # DEFECT CHECK: Outside click / backdrop click handler
    # Find outer backdrop element
    backdrop_match = re.search(r'<div className="fixed inset-0[^>]*>', content)
    has_backdrop_click = False
    if backdrop_match:
        tag = backdrop_match.group(0)
        has_backdrop_click = "onClick" in tag
    if not has_backdrop_click:
        log("DEFECT CONFIRMED: UserGuideModal outer backdrop lacks onClick handler (outside click does not close)!", "FAIL")
    else:
        log("UserGuideModal implements backdrop outside click close handler.", "PASS")

    return {
        "has_5_tabs": True,
        "has_escape_listener": has_escape_listener,
        "has_backdrop_click": has_backdrop_click,
    }

def test_format_picker_and_scan_type_desync():
    log("Stress-testing FormatPicker.tsx & NewScan.tsx scan-type transitions...")
    newscan_file = FRONTEND_SRC / "pages" / "NewScan.tsx"
    formatpicker_file = FRONTEND_SRC / "components" / "FormatPicker.tsx"

    newscan_content = newscan_file.read_text()
    formatpicker_content = formatpicker_file.read_text()

    # Check NewScan initial format state
    format_state_match = re.search(r'const\s*\[formats,\s*setFormats\]\s*=\s*useState<string\[\]>\((\[.*?\])\);', newscan_content)
    assert format_state_match, "formats state not found in NewScan.tsx"
    initial_formats = format_state_match.group(1)
    log(f"NewScan initial formats: {initial_formats}", "INFO")

    # Check if scanType change updates or resets formats
    # Look for useEffect or onSelect that sanitizes formats
    has_scan_type_effect = re.search(r'useEffect\(\s*\(\)\s*=>\s*\{[^}]*setFormats[^}]*\},\s*\[\s*scanType', newscan_content)
    has_scan_type_custom_setter = re.search(r'setScanType\([^\)]+\)[^;]*;[^}]*setFormats', newscan_content)

    if not has_scan_type_effect and not has_scan_type_custom_setter:
        log("DEFECT CONFIRMED: When scanType changes in NewScan.tsx, 'formats' is NOT sanitized!", "FAIL")
        log("  -> Switching to 'gaussian_splat' leaves ['glb', 'obj'] in formats state.", "FAIL")
        log("  -> Summary card renders 'GLB, OBJ' for 3DGS, and createJob submits invalid formats.", "FAIL")
        desync_defect = True
    else:
        log("NewScan updates formats on scanType change.", "PASS")
        desync_defect = False

    return {"desync_defect": desync_defect}

def test_jobs_pagination_and_unknown_status():
    log("Stress-testing Jobs.tsx pagination & unknown status...")
    jobs_file = FRONTEND_SRC / "pages" / "Jobs.tsx"
    jobs_content = jobs_file.read_text()

    # Check fetchJobs invocation
    fetch_match = re.search(r'fetchJobs\(\s*(\d+)\s*,\s*(\d+)\s*\)', jobs_content)
    assert fetch_match, "fetchJobs call not found in Jobs.tsx"
    limit, offset = fetch_match.groups()
    log(f"Jobs.tsx uses hardcoded fetchJobs(limit={limit}, offset={offset})", "INFO")

    # Check if there are pagination controls in Jobs.tsx
    has_pagination = ("page" in jobs_content.lower() and "next" in jobs_content.lower()) or "loadMore" in jobs_content or "setOffset" in jobs_content
    if not has_pagination:
        log(f"DEFECT CONFIRMED: Jobs.tsx has hardcoded limit={limit} and NO pagination or load-more controls! Scans > {limit} are inaccessible.", "FAIL")
    else:
        log("Jobs.tsx has pagination controls.", "PASS")

    # Check unknown status counting vs filtering
    # In line 74: jobs.filter(j => ["queued", "running", "preprocessing", "exporting"].includes(j.status))
    # In line 258: Failed ({totalCount - completedCount - runningCount})
    # In line 91: if (job.status !== "failed" && job.status !== "cancelled") return false;
    counting_math = "totalCount - completedCount - runningCount" in jobs_content
    filter_logic = 'job.status !== "failed" && job.status !== "cancelled"' in jobs_content

    if counting_math and filter_logic:
        log("DEFECT CONFIRMED: Unknown job status anomaly:", "FAIL")
        log("  -> If a job has status 'interrupted' or 'timeout', it is counted under 'Failed (N)' counter.", "FAIL")
        log("  -> But clicking the 'Failed' pill filters by (status === 'failed' || status === 'cancelled'), filtering out the job!", "FAIL")
        log("  -> Result: Failed pill displays 'Failed (1)', but clicking it shows empty list 'No matching reconstructions found'.", "FAIL")
        unknown_status_defect = True
    else:
        unknown_status_defect = False

    return {
        "has_pagination": has_pagination,
        "unknown_status_defect": unknown_status_defect,
    }

def test_measure_tool_zero_distance_guard():
    log("Stress-testing MeasureTool.tsx zero distance / identical points handling...")
    tool_file = FRONTEND_SRC / "components" / "MeasureTool.tsx"
    tool_content = tool_file.read_text()

    # Check getDistance math
    # const dx = pointA[0] - pointB[0];
    # const dy = pointA[1] - pointB[1];
    # const dz = pointA[2] - pointB[2];
    # return Math.sqrt(dx * dx + dy * dy + dz * dz);
    assert "dx = pointA[0] - pointB[0]" in tool_content
    assert "dy = pointA[1] - pointB[1]" in tool_content
    assert "dz = pointA[2] - pointB[2]" in tool_content
    log("MeasureTool Euclidean distance formula verified.", "PASS")

    # Check if handleApply guards against dist <= 1e-4 or identical points
    # handleApply:
    # const val = parseFloat(realDist);
    # if (isNaN(val) || val <= 0) ...
    handle_apply_match = re.search(r'const handleApply = async \(\) => \{(.*?)\};', tool_content, re.DOTALL)
    assert handle_apply_match, "handleApply not found in MeasureTool.tsx"
    apply_code = handle_apply_match.group(1)

    has_dist_check = "dist" in apply_code or "getDistance" in apply_code or "too close" in apply_code.lower()
    if not has_dist_check:
        log("DEFECT CONFIRMED: MeasureTool.tsx handleApply does NOT validate that virtual 'dist' > 0 before sending calibrate API request!", "FAIL")
        log("  -> When Point A and Point B are identical (dist = 0), Apply Scale button is enabled and triggers network request.", "FAIL")
        log("  -> Backend rejects with 400 'Selected points are too close together', but client.ts throws generic 'Failed submitting calibration', hiding real error from user.", "FAIL")
        dist_guard_defect = True
    else:
        log("MeasureTool guards against zero virtual distance.", "PASS")
        dist_guard_defect = False

    # Check client.ts calibrateScale error reporting
    client_file = FRONTEND_SRC / "api" / "client.ts"
    client_content = client_file.read_text()
    calibrate_fn = re.search(r'export async function calibrateScale\([\s\S]*?\): Promise<[\s\S]*?> \{([\s\S]*?)\n\}\n', client_content)
    assert calibrate_fn, "calibrateScale not found in client.ts"
    cal_code = calibrate_fn.group(1)
    parses_error_json = "res.json()" in cal_code and "detail" in cal_code
    if not parses_error_json:
        log("DEFECT CONFIRMED: client.ts calibrateScale ignores backend error detail and throws generic Error('Failed submitting calibration')!", "FAIL")
        client_error_defect = True
    else:
        log("client.ts calibrateScale parses error detail.", "PASS")
        client_error_defect = False

    return {
        "dist_guard_defect": dist_guard_defect,
        "client_error_defect": client_error_defect,
    }

def main():
    print("=" * 70)
    print("CHALLENGER 2 EMPIRICAL STRESS TEST HARNESS — MILESTONE M2")
    print("=" * 70)

    results = {}
    try:
        results["health"] = test_api_health()
        results["capabilities"] = test_api_capabilities()
        results["pagination"] = test_api_jobs_pagination_and_filters()
        results["calibrate_api"] = test_api_calibrate_edge_cases()
        results["user_guide"] = test_user_guide_modal_code()
        results["format_picker"] = test_format_picker_and_scan_type_desync()
        results["jobs_ui"] = test_jobs_pagination_and_unknown_status()
        results["measure_tool"] = test_measure_tool_zero_distance_guard()

        print("\n" + "=" * 70)
        print("SUMMARY OF EMPIRICAL FINDINGS")
        print("=" * 70)

        defects = []
        if not results["user_guide"]["has_escape_listener"]:
            defects.append("UserGuideModal lacks keyboard navigation: Escape key does not close modal")
        if not results["user_guide"]["has_backdrop_click"]:
            defects.append("UserGuideModal lacks backdrop click handler: clicking outside modal does not close it")
        if results["format_picker"]["desync_defect"]:
            defects.append("NewScan.tsx desynchronizes formats state when scanType changes (leaves unsupported formats like GLB/OBJ selected for 3DGS)")
        if not results["jobs_ui"]["has_pagination"]:
            defects.append("Jobs.tsx hardcodes limit=50 and lacks pagination controls; jobs > 50 are inaccessible in UI")
        if results["jobs_ui"]["unknown_status_defect"]:
            defects.append("Jobs.tsx counter vs filter discrepancy on unknown/non-standard job status")
        if results["measure_tool"]["dist_guard_defect"]:
            defects.append("MeasureTool.tsx enables and sends calibration on identical picked points (dist=0) without client pre-validation")
        if results["measure_tool"]["client_error_defect"]:
            defects.append("client.ts calibrateScale swallows backend HTTP 400 error detail, showing generic failure message")

        print(f"Total defects found: {len(defects)}")
        for i, d in enumerate(defects, 1):
            print(f"  {i}. {d}")

        if len(defects) > 0:
            print("\nVERDICT: REQUEST_CHANGES")
            return 1
        else:
            print("\nVERDICT: APPROVE")
            return 0

    except Exception as e:
        log(f"Test harness encountered unexpected error: {e}", "FAIL")
        import traceback
        traceback.print_exc()
        return 2

if __name__ == "__main__":
    sys.exit(main())
