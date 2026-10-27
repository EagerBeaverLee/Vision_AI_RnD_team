import tomllib
import re

# 1. 두 프로젝트의 pyproject.toml 경로 지정
path_main = r"pyproject.toml"
path_sub = r"D:\LEE\AI_team\github\Vision_AI_RnD_team\projects\env\uv_pj7\pyproject.toml"

with open(path_main, "rb") as f:
    deps_a = tomllib.load(f).get("project", {}).get("dependencies", [])
with open(path_sub, "rb") as f:
    deps_b = tomllib.load(f).get("project", {}).get("dependencies", [])

# 패키지 이름만 추출하는 정규식 (버전 제약 분리)
def get_pkg_name(dep):
    return re.split(r"[=><~^! ;]", dep)[0].lower()

names_a = {get_pkg_name(d) for d in deps_a}

# A에 없는 B만의 패키지 추출
to_add = []
for dep in deps_b:
    pkg_name = get_pkg_name(dep)
    if pkg_name not in names_a:
        # 버전 제약 없이 이름만 깔끔하게 추가하려면 pkg_name 사용
        # B의 제약조건을 그대로 가져오려면 dep 사용
        to_add.append(pkg_name)

print("\n=== 복사해서 실행할 uv add 명령어 ===")
print(f"uv add {' '.join(to_add)}")