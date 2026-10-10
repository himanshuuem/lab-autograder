// Lab Grader CI: test, build, isolation tests, throw-away stack + smoke test, optional deploy.
// Jenkins talks to the host's Docker. Bind mounts would resolve on the host,
// so tests run inside an image built from the workspace instead.
pipeline {
  agent any
  options { timestamps(); timeout(time: 60, unit: 'MINUTES'); disableConcurrentBuilds() }
  parameters {
    booleanParam(name: 'DEPLOY', defaultValue: false, description: 'After all checks pass, (re)deploy the live stack on this host')
  }
  environment {
    CI_PROJECT = "agci${env.BUILD_NUMBER}"
  }
  stages {
    stage('Checkout') {
      steps {
        deleteDir()
        // the repository is mounted read-only at /repo (see docker-compose.yml)
        sh 'cp -a /repo/. . && rm -f .env && rm -rf secrets backups'
      }
    }
    stage('Unit tests') {
      steps {
        sh 'docker build -f ci/Dockerfile.test -t autograder-test:ci .'
        sh 'docker run --rm autograder-test:ci'
      }
    }
    stage('Build images') {
      steps {
        sh 'python3 scripts/init_env.py >/dev/null && cp .env ci.env'
        sh 'docker compose --env-file ci.env --profile images build runner-python runner-gcc runner-java'
        sh 'docker compose --env-file ci.env build sandbox mcp app'
      }
    }
    stage('Sandbox isolation') {
      steps {
        sh '''docker run --rm -v /var/run/docker.sock:/var/run/docker.sock autograder-test:ci \
              bash -c "cd sandbox && python -m pytest -m docker -v tests/test_isolation_docker.py"'''
      }
    }
    stage('Throw-away stack + smoke test') {
      steps {
        sh '''
          sed -i 's/^APP_PORT=.*/APP_PORT=0/' ci.env
          docker compose -p "$CI_PROJECT" --env-file ci.env up -d db sandbox mcp app
          PW=$(grep '^ADMIN_PASSWORD=' ci.env | cut -d= -f2-)
          docker run --rm --network "${CI_PROJECT}_default" autograder-test:ci \
            python scripts/smoke.py http://app:8000 ta "$PW"
        '''
      }
      post {
        always {
          sh 'docker compose -p "$CI_PROJECT" --env-file ci.env logs --no-color app sandbox mcp > stack.log 2>&1 || true'
          archiveArtifacts artifacts: 'stack.log', allowEmptyArchive: true
          sh 'docker compose -p "$CI_PROJECT" --env-file ci.env down -v || true'
        }
      }
    }
    stage('Deploy') {
      when { expression { return params.DEPLOY } }
      steps {
        // uses the real .env from the mounted repository
        sh 'cp /repo/.env .env'
        sh 'docker compose -p autograder --profile images build runner-python runner-gcc runner-java'
        sh 'docker compose -p autograder up -d --build db sandbox mcp app'
      }
    }
  }
  post {
    always { sh 'rm -f ci.env .env || true' }
  }
}
