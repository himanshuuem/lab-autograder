// Grade one Classroom assignment through the running dashboard and archive the CSV.
pipeline {
  agent any
  options { timestamps(); timeout(time: 90, unit: 'MINUTES') }
  parameters {
    string(name: 'COURSE_ID', defaultValue: '', description: 'Google Classroom course id (blank = first course)')
    string(name: 'ASSIGNMENT_ID', defaultValue: '', description: 'Classroom coursework id (blank = first assignment)')
    booleanParam(name: 'PUBLISH_DRAFT', defaultValue: false, description: 'Also save scores as draft grades in Classroom')
  }
  stages {
    stage('Grade') {
      steps {
        deleteDir()
        sh 'cp /repo/.env .env'
        sh 'docker image inspect autograder-test:ci >/dev/null 2>&1 || docker build -f /repo/ci/Dockerfile.test -t autograder-test:ci /repo'
        sh '''
          PW=$(grep '^ADMIN_PASSWORD=' .env | cut -d= -f2-)
          USER=$(grep '^ADMIN_USER=' .env | cut -d= -f2-)
          docker run --rm --network autograder_default autograder-test:ci \
            python scripts/grade.py http://app:8000 "${USER:-ta}" "$PW" "$COURSE_ID" "$ASSIGNMENT_ID" \
            $( [ "$PUBLISH_DRAFT" = true ] && echo --publish-draft ) --stdout-csv > grades.csv
        '''
        archiveArtifacts artifacts: 'grades.csv'
      }
    }
  }
  post { always { sh 'rm -f .env' } }
}
