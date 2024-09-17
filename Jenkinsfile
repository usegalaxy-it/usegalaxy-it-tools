pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '7'))
    }

    stages {
        stage('Checkout') {
            steps {
                // Change <repo_ssh_key>
                checkout([$class: 'GitSCM',
                    branches: [[name: '*/master']],
                    doGenerateSubmoduleConfigurations: false,
                    extensions: [[$class: 'CleanCheckout']],
                    userRemoteConfigs: [[credentialsId: '<repo_ssh_key>', url: 'git@github.com:usegalaxy-it/usegalaxy-it-tools.git']]
                ])
            }
        }

        stage('Build') {
            steps {
                deleteDir()
                // Change <api_key>
                withCredentials([file(credentialsId: '<api_key>', variable: 'API_KEY')]) {
                    withPythonEnv('Python-3.8.10') {
                        sh 'pip install -r requirements.txt'
                        sh 'make fix'
                        sh 'make install GALAXY_SERVER=<http://...> GALAXY_API_KEY=${API_KEY}'
                        sh 'git add *.yaml.lock'
                        sh 'git commit -m "Update lock files. Jenkins Build: ${BUILD_NUMBER}" -m "https://github.com/usegalaxy-it/usegalaxy-it-tools-reports/blob/main/reports/$(date +%Y-%m-%d-%H-%M)-tool-update.md" || true'
                    }
                }
            }
        }
    }

    post {
        // Change <repo_ssh_key>
        success {
            archiveArtifacts artifacts: 'report.log', onlyIfSuccessful: true
            git branch: 'master', credentialsId: '<repo_ssh_key>', pushOnlyIfSuccess: true, url: 'git@github.com:usegalaxy-it/usegalaxy-it-tools.git'
        }
        // Change admin email
        always {
            emailext body: '', recipientProviders: [[$class: 'DevelopersRecipientProvider'], [$class: 'RequesterRecipientProvider']], subject: "${env.JOB_NAME} - Build #${env.BUILD_NUMBER} - ${currentBuild.currentResult}", to: '<admin@gmail.com>', sendToIndividuals: true, unstable: true
        }
    }
}
