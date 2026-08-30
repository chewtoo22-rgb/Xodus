#!/usr/bin/env python3
import importlib.util, json, tempfile
from pathlib import Path
SPEC=importlib.util.spec_from_file_location("labs_validator",Path(__file__).parents[1]/"scripts"/"xodus-labs-validate.py"); mod=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(mod)
BASE={"schema_version":1,"id":"001-test","name":"Test Lab","stage":"incubator","enabled_by_default":False,"boot_dependency":False,"login_dependency":False,"installer_dependency":False,"recovery_dependency":False,"network_required":False,"permissions":[]}
def fixture(overrides=None):
    temp=tempfile.TemporaryDirectory(); root=Path(temp.name)/"labs"; project=root/"001-test"; project.mkdir(parents=True); data=dict(BASE); data.update(overrides or {}); (project/"lab.json").write_text(json.dumps(data),encoding="utf-8"); return temp,root
def expect_fail(overrides):
    temp,root=fixture(overrides)
    try:
        try: mod.validate_labs(root)
        except ValueError: return
        raise AssertionError(f"expected failure for {overrides}")
    finally: temp.cleanup()
def main():
    temp,root=fixture()
    try: assert mod.validate_labs(root)[0]["id"]=="001-test"
    finally: temp.cleanup()
    for bad in ({"enabled_by_default":True},{"boot_dependency":True},{"login_dependency":True},{"installer_dependency":True},{"recovery_dependency":True},{"stage":"production-ish"},{"permissions":["shell"]*33},{"permissions":["shell","shell"]},{"id":"999-wrong"}): expect_fail(bad)
    print("PASS: AI Labs isolation contract")
if __name__=="__main__": main()
