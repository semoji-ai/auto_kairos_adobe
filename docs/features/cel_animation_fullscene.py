import sys,glob,os,re,shutil,subprocess,time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,"/Users/jleavens_macmini/LocalProjects/auto_kairos_adobe/.claude/worktrees/imagegen-builtin-layers")
from pathlib import Path
from PIL import Image
from backend import imagegen
HOME=Path.home(); GEN=HOME/".codex/generated_images"; W=HOME/"cel_full"; SC=str(W/"scene.png")
SS=Image.open(SC).size; ENV={k:v for k,v in os.environ.items() if k!="OPENAI_API_KEY"}
L=W/"_log.txt"; L.write_text("start\n")
def log(m): L.open("a").write(str(m)[:120]+"\n")
poses=[
 "비커를 가슴 높이에 들고 정면을 본다",
 "비커를 어깨 높이로 살짝 들어올리며 시선이 비커로 향한다",
 "비커를 눈높이로 들어올려 올려다본다",
 "눈높이의 비커를 살짝 기울여 유심히 관찰하며 미소 짓는다",
 "비커를 다시 어깨 높이로 내린다",
 "비커를 가슴 높이로 내리고 정면을 본다",
]
def gen(i):
    out=W/f"f{i}.png"
    prompt=(f"{imagegen.load_style()}\n첨부한 1번 씬 이미지를 레퍼런스로 사용한다. 동일한 1968 3M 화학 연구실 장면을 다시 그린다. "
      f"배경(3M 로고 포스터·항공기 도면·유리 플라스크·시험관대·페트리접시·갈색 시약병·현미경·실험대·벽 색)과 구도·색감·조명·카메라 프레이밍은 "
      f"원본과 100% 동일하게 유지한다. 인물 스펜서 실버(흰 실험복)의 동작만 변경한다: {pose if (pose:=poses[i]) else ''}. "
      f"풀 씬(배경 포함) 한 장. 텍스트 없음.")
    cmd=["codex","-a","never","--enable","image_generation","exec","--json","--skip-git-repo-check","--ephemeral","-s","workspace-write","-C",str(W),"-i",SC,"-"]
    p=subprocess.run(cmd,input="/imagegen "+prompt,capture_output=True,text=True,env=ENV)
    m=re.search(r'"thread_id":"([a-z0-9-]+)"',p.stdout)
    if not m: log(f"f{i} FAIL"); return
    pn=sorted(glob.glob(str(GEN/m.group(1)/"*.png")),key=os.path.getmtime)
    shutil.copy(pn[-1],out); Image.open(out).convert("RGB").resize(SS,Image.LANCZOS).save(out)
    log(f"f{i} OK")
t0=time.time()
with ThreadPoolExecutor(max_workers=6) as ex: list(ex.map(gen,range(len(poses))))
log(f"gen {time.time()-t0:.0f}s")
fr=[Image.open(W/f"f{i}.png").convert("RGB") for i in range(len(poses)) if (W/f"f{i}.png").exists()]
if fr:
    seq=fr+fr[-2:0:-1]
    seq[0].save(W/"cel_full.gif",save_all=True,append_images=seq[1:],duration=200,loop=0)
    cols=len(fr); cw=SS[0]//3
    sheet=Image.new("RGB",(cw*cols,SS[1]//3),(255,255,255))
    for j,f in enumerate(fr): sheet.paste(f.resize((cw,SS[1]//3)),(j*cw,0))
    sheet.save(W/"contact.png"); log(f"{len(fr)} frames → cel_full.gif + contact.png")
