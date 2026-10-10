// Job DSL, loaded by Configuration as Code at startup.
// Pipelines are read from the repository mounted at /repo; restart Jenkins
// (make up-ci) after editing a Jenkinsfile.

pipelineJob('autograder-ci') {
  description('Unit tests, image build, sandbox isolation tests, throw-away stack with smoke test. Tick DEPLOY to update the live stack.')
  definition {
    cps {
      script(new File('/repo/Jenkinsfile').text)
      sandbox(true)
    }
  }
  properties {
    pipelineTriggers {
      triggers {
        cron { spec('H 2 * * *') }   // nightly
      }
    }
  }
}

pipelineJob('grade-assignment') {
  description('Grade a Classroom assignment through the running dashboard and archive the CSV of results.')
  definition {
    cps {
      script(new File('/repo/ci/grade.Jenkinsfile').text)
      sandbox(true)
    }
  }
}
