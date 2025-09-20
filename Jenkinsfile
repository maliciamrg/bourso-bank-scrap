pipeline {
    agent any
    stages {
        stage('Clean WorkSpace') {
            steps {
                // Clean before build
                cleanWs()
                // We need to explicitly checkout from SCM here
                checkout scm
                echo "Building ${env.JOB_NAME}..."
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
        python3 -m venv venv
        venv/bin/pip install --upgrade pip
        venv/bin/pip install -r requirements.txt
        '''
            }
        }

        stage('Get Version from Python Script') {
            steps {
                script {
                    // Extract __version__ using python -c
                    IMAGE_TAG = sh(
                            script: "venv/bin/python3 -c 'from BoursoBankScrap import __version__; print(__version__)'",
                            returnStdout: true
                    ).trim()
                    echo "Using Docker image tag: ${IMAGE_TAG}"
                }
            }
        }

        stage('Docker Build') {
            steps {
                script {
                    echo "Building Docker image ..."
                    withCredentials([usernamePassword(credentialsId: 'hub.docker.com', passwordVariable: 'HUB_REPO_PASS', usernameVariable: 'HUB_REPO_USER')]) {
                        def user = env.HUB_REPO_USER
                        def password = env.HUB_REPO_PASS
                        sh "docker version"
                        sh "docker login -u $user -p $password"
                        sh "docker build -t maliciamrg/bourso-bank-scrap:${IMAGE_TAG} ."
                        sh "docker push maliciamrg/bourso-bank-scrap:${IMAGE_TAG}"
                        sleep 10 // Wait for 10 seconds
                    }
                }
            }
        }


    }
    post {
        always {
            print "always"
        }
        changed {
            print "changed"
        }
        fixed {
            print "fixed"
            discordSend(description: "Jenkins Pipeline Build",
                    footer: "Status fixed",
                    link: env.BUILD_URL,
                    result: currentBuild.currentResult,
                    title: JOB_NAME,
                    webhookURL: "https://discord.com/api/webhooks/1251803129004032030/Ms-4v3aw3MMkIHIECMYMiP48NTV_F1IazsvwQmAqGGFw4OOR9FRX-DwjFG5V1dV-zKg6")
        }
        regression {
            print "regression"
        }
        aborted {
            print "aborted"
        }
        failure {
            print "failure"
            script {
                if (!currentBuild.getBuildCauses('hudson.model.Cause$UserIdCause')) {
                    discordSend(description: "Jenkins Pipeline Build",
                            footer: "Status failure",
                            link: env.BUILD_URL,
                            result: currentBuild.currentResult,
                            title: JOB_NAME,
                            webhookURL: "https://discord.com/api/webhooks/1251803129004032030/Ms-4v3aw3MMkIHIECMYMiP48NTV_F1IazsvwQmAqGGFw4OOR9FRX-DwjFG5V1dV-zKg6")
                }
            }
        }
        success {
            print "success"
        }
        unstable {
            print "unstable"
        }
        unsuccessful {
            print "unsuccessful"
        }
        cleanup {
            print "cleanup"
        }
    }
}