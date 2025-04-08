pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '5'))
    }

    stages {
        stage('Checkout') {
            steps {
                // CHECK CREDS AND URL
                checkout([$class: 'GitSCM',
                    branches: [[name: '*/main']],
                    doGenerateSubmoduleConfigurations: false,
                    extensions: [[$class: 'CleanCheckout']],
                    userRemoteConfigs: [[credentialsId: '<github_ssh_creds>', url: 'git@github.com:usegalaxy-it/usegalaxy.it-tools-reports.git']]
                ])
            }
        }

        stage('Build') {
            steps {
                deleteDir()
                // Setup ShiningPanda virtualenv, CHECK THE PATHS BELOW
                withPythonEnv('Python-3.8.10') {
                    sh 'git checkout main'
                    sh 'mkdir reports-$(date +%Y-%m) || true'
                    sh 'POST="$(date +%Y-%m-%d-%H-%M)-tools-update.md"'
                    sh 'cat /home/ubuntu/workspace/usegalaxy.it-tools/report.log | python /home/ubuntu/workspace/usegalaxy.it-tools/scripts/generate-report.py > reports-$(date +%Y-%m)/${POST}'
                    sh 'git add .'
                    sh 'git commit -m "Jenkins Build: ${BUILD_NUMBER}"'
                }
            }
        }
    }

    post {
        success {
            // CHECK CREDS AND URL
            git branch: 'main', credentialsId: '<github_ssh_creds>', pushOnlyIfSuccess: true, url: 'git@github.com:usegalaxy-it/usegalaxy.it-tools-reports.git'
        }
    }
}
