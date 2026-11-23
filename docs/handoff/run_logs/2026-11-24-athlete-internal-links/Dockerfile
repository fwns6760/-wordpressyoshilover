FROM asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/prosports-weekly-seo-check:weekly-20261106-t90
WORKDIR /app
RUN python3 -c "import hashlib; from pathlib import Path; assert hashlib.sha256(Path('src/prosports_weekly_seo_check.py').read_bytes()).hexdigest() == 'a2648b83aa878652cd99aae49a05e63a2582ff3f5eb16f09375b45aa510f19a9', 'Unexpected live source; refuse unrelated replacement'"
COPY prosports_weekly_seo_check.py /app/src/prosports_weekly_seo_check.py
