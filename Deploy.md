# 배포 안내

## 1. 배포 대상

이 문서는 다음 환경에 머신러닝 중간고사 연습 사이트를 배포하는 절차를 설명한다.

- 서버: Cafe24 가상서버 호스팅
- 권장 운영체제: Ubuntu 24.04 LTS 또는 22.04 LTS 64비트
- 서버 자원: RAM 1GB, SSD 30GB
- 도메인: `yangsong.cloud`
- 애플리케이션: Flask와 Gunicorn
- 실행 방식: Docker Compose
- 외부 연결: Nginx 리버스 프록시와 HTTPS

명령 예시에서 `<서버_공인_IP>`, `<저장소_URL>`, `<관리자_이메일>`은 실제 값으로 바꿔야 한다. 비밀번호, 세션 서명키, API 토큰과 개인키는 저장소에 기록하지 않는다.

## 2. 배포 구조

```mermaid
flowchart LR
    U[사용자] -->|HTTPS 443| N[Nginx]
    N -->|HTTP 127.0.0.1:8000| G[Gunicorn 컨테이너]
    G --> F[Flask 애플리케이션]
    F --> J[(Docker 문제 데이터 볼륨)]
```

Nginx만 인터넷에 공개하고 Gunicorn의 8000번 포트는 서버 내부에서만 접근하게 한다. `docker-compose.yml`은 `127.0.0.1:8000:8000`으로 설정되어 있으므로 외부에서 Gunicorn 포트에 직접 접속할 수 없다.

## 3. 배포 전 준비

### DNS 설정

도메인의 DNS 관리 화면에서 다음 레코드를 등록한다.

| 종류 | 이름 | 값 |
| --- | --- | --- |
| `A` | `@` | `<서버_공인_IP>` |

`www.yangsong.cloud`도 사용할 경우 다음 레코드를 추가한다.

| 종류 | 이름 | 값 |
| --- | --- | --- |
| `CNAME` | `www` | `yangsong.cloud` |

DNS 전파 여부는 로컬 컴퓨터에서 확인한다.

```powershell
Resolve-DnsName yangsong.cloud
```

반환된 IPv4 주소가 서버 공인 IP와 같아진 후 인증서를 발급한다.

### 로컬 검증

배포할 커밋에서 자동화 테스트와 컨테이너 실행을 먼저 확인한다.

먼저 `.env.example`을 `.env`로 복사하고 로컬 테스트용 관리자 비밀번호와 세션 서명키를 설정한다. `.env`는 Git에서 제외되어 있다.

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
.\.venv\Scripts\python.exe -m pytest -q
docker compose up --build -d
curl.exe --fail http://127.0.0.1:8000/
docker compose logs --no-color --tail 50 web
```

검증 후 로컬 컨테이너를 중지하려면 다음 명령을 실행한다.

```powershell
docker compose down
```

## 4. 서버 초기 설정

### 서버 접속과 패키지 갱신

로컬 컴퓨터에서 SSH로 접속한다.

```powershell
ssh <서버_사용자>@<서버_공인_IP>
```

서버에서 운영체제 패키지를 갱신하고 필수 도구를 설치한다.

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl git nginx ufw certbot python3-certbot-nginx
```

커널 패키지가 갱신된 경우 서버를 재부팅한 뒤 다시 접속한다.

```bash
sudo reboot
```

### Docker 설치

운영 서버에는 배포판의 비공식 Docker 패키지 대신 Docker 공식 APT 저장소를 사용한다. 다음 절차는 Docker 공식 Ubuntu 설치 방식이다.

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

다음 내용으로 `/etc/apt/sources.list.d/docker.sources`를 작성한다. `Suites` 값은 서버의 Ubuntu 코드명으로 대체한다. 코드명은 `. /etc/os-release && echo "$VERSION_CODENAME"` 명령으로 확인할 수 있다.

```text
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
```

ARM 서버라면 `Architectures`를 `arm64`로 바꾼다. Ubuntu 22.04라면 `Suites`를 `jammy`로 바꾼다.

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

이 문서에서는 Docker 소켓 권한을 일반 사용자에게 부여하지 않고 `sudo docker`를 사용한다. Docker 그룹은 사실상 관리자 수준의 권한을 제공하므로 편의만을 위해 사용자를 추가하지 않는다.

### 방화벽 설정

SSH 접속 허용 규칙을 먼저 추가한 후 방화벽을 활성화한다. SSH 포트가 22번이 아니라면 실제 포트로 바꾼다.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status verbose
```

8000번 포트는 방화벽에서 공개하지 않는다. Docker가 공개한 포트는 UFW 규칙을 우회할 수 있으므로 Compose의 포트 바인딩도 반드시 `127.0.0.1`로 제한한다.

## 5. 애플리케이션 배치

### 소스 내려받기

애플리케이션은 `/srv/ml_class_mid_exam`에 배치한다.

```bash
sudo mkdir -p /srv/ml_class_mid_exam
sudo chown "$USER":"$USER" /srv/ml_class_mid_exam
git clone <저장소_URL> /srv/ml_class_mid_exam
cd /srv/ml_class_mid_exam
```

비공개 저장소라면 서버 전용 읽기 키 또는 제한된 배포 자격 증명을 사용한다. 개인 계정의 범용 토큰을 서버에 평문으로 저장하지 않는다.

### 관리자 인증 환경변수

프로젝트 루트에서 소유자만 읽을 수 있는 `.env` 파일을 준비한다.

```bash
cd /srv/ml_class_mid_exam
umask 077
touch .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
chmod 600 .env
```

출력된 난수를 `SECRET_KEY`에 사용하고, `.env`를 다음 형식으로 작성한다. 관리자 비밀번호는 12자 이상으로 충분히 길고 다른 서비스에서 사용하지 않은 값으로 정한다.

```dotenv
ADMIN_PASSWORD=<관리자_비밀번호>
SECRET_KEY=<생성한_64자리_난수>
SESSION_COOKIE_SECURE=1
```

실제 값을 명령줄 인수나 셸 기록에 남기지 않는다. `.env`를 저장소에 추가하거나 다른 사용자에게 읽기 권한을 주지 않는다. `SECRET_KEY`를 변경하면 기존 관리자 세션은 모두 무효화된다.

### 운영 포트 제한

`docker-compose.yml`의 포트와 관리자 환경변수, 문제 데이터 볼륨 설정이 다음과 같은지 확인한다.

```yaml
services:
  web:
    build: .
    restart: unless-stopped
    environment:
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:?ADMIN_PASSWORD 환경변수를 설정해야 합니다}
      SECRET_KEY: ${SECRET_KEY:?SECRET_KEY 환경변수를 설정해야 합니다}
      SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-0}
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - question_data:/app/data

volumes:
  question_data:
```

구성 파일이 유효한지 확인한다.

```bash
sudo docker compose config --quiet
```

### 이미지 빌드와 실행

```bash
sudo docker compose build --pull
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --no-color --tail 100 web
```

컨테이너가 비루트 사용자로 실행되고 홈 화면이 응답하는지 확인한다.

```bash
sudo docker compose exec -T web id
curl --fail --show-error http://127.0.0.1:8000/
```

`id` 결과에 `appuser`가 표시되고 HTTP 요청이 성공해야 다음 단계로 진행한다.

## 6. Nginx 리버스 프록시

다음 내용으로 `/etc/nginx/sites-available/yangsong.cloud`를 작성한다.

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name yangsong.cloud;

    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
```

`www.yangsong.cloud`도 사용할 경우 `server_name`을 다음과 같이 작성하고 인증서 발급 명령에도 도메인을 추가한다.

```nginx
server_name yangsong.cloud www.yangsong.cloud;
```

사이트를 활성화하고 문법을 검사한다.

```bash
sudo ln -s /etc/nginx/sites-available/yangsong.cloud /etc/nginx/sites-enabled/yangsong.cloud
sudo nginx -t
sudo systemctl reload nginx
curl --fail --show-error http://yangsong.cloud/
```

이미 같은 이름의 심볼릭 링크가 있다면 `ln` 명령을 다시 실행하지 않는다.

## 7. HTTPS 인증서

DNS가 서버를 가리키고 80번과 443번 포트가 열려 있는 상태에서 인증서를 발급한다.

```bash
sudo certbot --nginx -d yangsong.cloud -m <관리자_이메일> --agree-tos --no-eff-email --redirect
```

`www` 도메인도 등록했다면 다음 명령을 사용한다.

```bash
sudo certbot --nginx -d yangsong.cloud -d www.yangsong.cloud -m <관리자_이메일> --agree-tos --no-eff-email --redirect
```

인증서와 자동 갱신 상태를 확인한다.

```bash
sudo certbot certificates
sudo systemctl status certbot.timer
sudo certbot renew --dry-run
curl --fail --show-error https://yangsong.cloud/
```

## 8. 배포 후 점검

### 기능 점검

다음 항목을 브라우저와 명령줄에서 확인한다.

1. `https://yangsong.cloud/`에서 분야 목록이 표시된다.
2. 분야별 문제 화면으로 이동한다.
3. 답안을 제출하면 점수와 해설이 표시된다.
4. 문제 작성 양식에서 JSON 파일을 내려받을 수 있다.
5. `/admin`은 로그인하지 않은 사용자를 로그인 화면으로 이동시킨다.
6. 관리자 로그인 후 분야 추가와 문제 추가·수정·삭제가 정상 동작한다.
7. 존재하지 않는 분야는 `404`를 반환한다.

```bash
curl --fail --show-error --head https://yangsong.cloud/
curl --silent --output /dev/null --write-out '%{http_code}\n' 'https://yangsong.cloud/quiz?category=unknown'
```

두 번째 명령은 `404`를 출력해야 한다.

### 상태와 자원 점검

```bash
sudo docker compose ps
sudo docker compose logs --no-color --tail 100 web
sudo docker stats --no-stream
free -h
df -h
sudo systemctl status nginx --no-pager
```

RAM 1GB 서버에서는 메모리 부족 종료 여부를 주기적으로 확인한다.

```bash
sudo journalctl -k --grep='Out of memory' --since '24 hours ago'
```

## 9. 업데이트 배포

배포 전 현재 커밋을 기록해 두면 문제 발생 시 되돌리기 쉽다.

```bash
cd /srv/ml_class_mid_exam
git rev-parse HEAD
git pull --ff-only
sudo docker compose build --pull
sudo docker compose up -d
curl --fail --show-error http://127.0.0.1:8000/
sudo docker compose logs --no-color --tail 100 web
```

이 구성은 웹 컨테이너가 하나이므로 재생성 중 짧은 중단이 발생할 수 있다. 배포가 확인된 후에만 사용하지 않는 이미지를 정리한다.

```bash
sudo docker image prune
```

`docker system prune`이나 볼륨 삭제 옵션은 다른 서비스 데이터까지 제거할 수 있으므로 사용하지 않는다.

## 10. 문제 데이터 갱신과 백업

문제와 분야 데이터는 Docker의 `question_data` 이름 있는 볼륨에 저장된다. 새 볼륨은 이미지의 기본 JSON으로 초기화된다. 기존 볼륨에 분야 파일이 없으면 애플리케이션 시작 시 이미지의 기본 분야 데이터로 `/app/data/categories.json`을 생성한다. 이후 관리 화면에서 변경한 내용은 컨테이너를 재생성하거나 이미지를 갱신해도 유지된다. Docker 볼륨의 이 동작은 [Docker 공식 볼륨 문서](https://docs.docker.com/engine/storage/volumes/)에서 확인할 수 있다.

```bash
cd /srv/ml_class_mid_exam
mkdir -p backups
chmod 700 backups
sudo docker compose exec -T web sh -c 'cat /app/data/questions.json' > backups/questions-YYYYMMDD-HHMMSS.json
sudo docker compose exec -T web sh -c 'cat /app/data/categories.json' > backups/categories-YYYYMMDD-HHMMSS.json
python3 -m json.tool backups/questions-YYYYMMDD-HHMMSS.json > /dev/null
python3 -m json.tool backups/categories-YYYYMMDD-HHMMSS.json > /dev/null
```

`YYYYMMDD-HHMMSS`는 실제 백업 시각으로 바꾼다. 관리자 변경 데이터는 Git 저장소에 자동 반영되지 않으므로 배포 전후와 문제 일괄 변경 전에 별도로 백업한다. `docker compose down -v`는 문제 데이터 볼륨을 삭제하므로 실행하지 않는다.

백업을 복원할 때는 먼저 JSON 형식을 검사하고 웹 컨테이너를 중지한다.

```bash
python3 -m json.tool backups/questions-YYYYMMDD-HHMMSS.json > /dev/null
python3 -m json.tool backups/categories-YYYYMMDD-HHMMSS.json > /dev/null
sudo docker compose stop web
sudo docker compose run --rm -T web sh -c 'cat > /app/data/questions.json' < backups/questions-YYYYMMDD-HHMMSS.json
sudo docker compose run --rm -T web sh -c 'cat > /app/data/categories.json' < backups/categories-YYYYMMDD-HHMMSS.json
sudo docker compose up -d
curl --fail --show-error http://127.0.0.1:8000/
```

사용자 답안과 점수는 서버에 저장되지 않으므로 별도의 사용자 데이터 백업은 없다.

## 11. 장애 대응과 복구

### 컨테이너가 실행되지 않을 때

```bash
cd /srv/ml_class_mid_exam
sudo docker compose ps --all
sudo docker compose logs --no-color --tail 200 web
sudo docker compose config --quiet
```

문제 JSON 오류가 의심되면 볼륨에 저장된 파일을 복사해 형식을 확인한다.

```bash
sudo docker compose exec -T web sh -c 'cat /app/data/questions.json' > /tmp/questions-check.json
sudo docker compose exec -T web sh -c 'cat /app/data/categories.json' > /tmp/categories-check.json
python3 -m json.tool /tmp/questions-check.json > /dev/null
python3 -m json.tool /tmp/categories-check.json > /dev/null
```

### Nginx가 응답하지 않을 때

```bash
sudo nginx -t
sudo systemctl status nginx --no-pager
sudo journalctl -u nginx --since '30 minutes ago' --no-pager
curl --fail --show-error http://127.0.0.1:8000/
```

로컬 8000번 요청은 성공하지만 외부 요청이 실패하면 Nginx 설정, DNS, 방화벽과 인증서를 확인한다.

### 이전 버전으로 복구

업데이트 직전에 기록한 정상 커밋을 `<정상_커밋>`에 지정한다. 작업 중인 변경 사항이 없는지 먼저 확인한다.

```bash
cd /srv/ml_class_mid_exam
git status --short
git switch --detach <정상_커밋>
sudo docker compose up --build -d
curl --fail --show-error http://127.0.0.1:8000/
```

복구 후 원인을 수정한 새 커밋을 기본 브랜치에 반영하고 다시 배포한다. 운영 서버에서 `git reset --hard`로 변경 사항을 강제로 지우지 않는다.

## 12. 운영 체크리스트

- [ ] DNS `A` 레코드가 서버 공인 IP를 가리킨다.
- [ ] Docker Engine과 Compose 플러그인이 정상 동작한다.
- [ ] `.env`에 관리자 비밀번호와 무작위 세션 서명키가 설정되어 있고 권한이 `600`이다.
- [ ] Compose 포트가 `127.0.0.1:8000:8000`으로 제한되어 있다.
- [ ] 컨테이너가 `appuser`로 실행된다.
- [ ] 관리자 로그인과 분야 추가 및 문제 추가·수정·삭제가 정상 동작한다.
- [ ] 분야와 문제 데이터 볼륨의 백업 및 복원 절차를 확인했다.
- [ ] Nginx 설정 문법 검사를 통과한다.
- [ ] UFW에서 SSH, HTTP, HTTPS만 허용한다.
- [ ] HTTPS 접속과 인증서 자동 갱신 테스트가 성공한다.
- [ ] 홈, 문제 풀이, 채점, 문제 작성 화면이 정상 동작한다.
- [ ] 컨테이너 로그에 반복 오류가 없다.
- [ ] 배포 커밋과 복구 대상 커밋을 기록했다.

## 13. 참고 문서

- [Docker Engine Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/)
- [Docker Compose 플러그인 설치](https://docs.docker.com/compose/install/linux/)
- [Docker Compose 환경변수 보간](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
- [Nginx 프록시 모듈](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [Certbot 공식 문서](https://eff-certbot.readthedocs.io/en/stable/)
- [Ubuntu 방화벽 안내](https://ubuntu.com/server/docs/how-to/security/firewalls/)
- [Flask 보안 고려사항](https://flask.palletsprojects.com/en/stable/web-security/)
