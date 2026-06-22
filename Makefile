.PHONY: help bootstrap reset cluster-up cluster-down helm-repos \
        build build-ml build-proxy build-all \
        load load-ml load-proxy load-all \
        deploy deploy-all deploy-ml deploy-proxy deploy-monitoring deploy-adapter deploy-rules deploy-hpa \
        logs-a logs-b logs-otel logs-ml logs-proxy \
        restart-ml restart-proxy ml-cycle proxy-cycle \
        forward-prometheus forward-grafana forward-proxy forward-a forward-b \
        redis-cli redis-keys redis-flush hpa-status traffic-test status

help:
	@echo "Common targets:"
	@echo "  make bootstrap    Full setup from a fresh cluster"
	@echo "  make reset        Tear down and rebuild everything"
	@echo "  make ml-cycle     Rebuild + redeploy ml-service"
	@echo "  make proxy-cycle  Rebuild + redeploy proxy"
	@echo "  make status       Show all pods and HPA state"

bootstrap: cluster-up helm-repos build-all load-all deploy-monitoring deploy-all
	@python -c "import time; time.sleep(30)"
	$(MAKE) deploy-adapter
	$(MAKE) deploy-rules
	$(MAKE) deploy-hpa
	@$(MAKE) status

reset: cluster-down bootstrap

cluster-up:
	kind create cluster --config k8s/kind-config.yaml

cluster-down:
	-kind delete cluster --name balancit
	-docker system prune -af --volumes

helm-repos:
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update

build:
	docker build -t service-a:latest backend-services/service-a/
	docker build -t service-b:latest backend-services/service-b/

build-ml:
	docker build -t ml-service:latest ml/

build-proxy:
	docker build -t proxy:latest proxy/

build-all: build build-ml build-proxy

load:
	kind load docker-image service-a:latest --name balancit
	kind load docker-image service-b:latest --name balancit

load-ml:
	kind load docker-image ml-service:latest --name balancit

load-proxy:
	kind load docker-image proxy:latest --name balancit

load-all: load load-ml load-proxy

deploy:
	kubectl apply -f k8s/base/namespace.yaml
	kubectl apply -f k8s/base/service-a.yaml
	kubectl apply -f k8s/base/service-b.yaml
	kubectl apply -f k8s/base/otel-collector.yaml

deploy-all:
	kubectl apply -f k8s/base/namespace.yaml
	kubectl apply -f k8s/base/redis.yaml
	kubectl rollout status deployment/redis -n balancit
	kubectl apply -f k8s/base/service-a.yaml
	kubectl apply -f k8s/base/service-b.yaml
	kubectl apply -f k8s/base/otel-collector.yaml
	kubectl apply -f k8s/base/ml-service.yaml
	kubectl apply -f k8s/base/proxy.yaml
	kubectl rollout status deployment/ml-service -n balancit
	kubectl rollout status deployment/proxy -n balancit

deploy-ml:
	kubectl apply -f k8s/base/ml-service.yaml
	kubectl rollout status deployment/ml-service -n balancit

deploy-proxy:
	kubectl apply -f k8s/base/proxy.yaml
	kubectl rollout status deployment/proxy -n balancit

deploy-monitoring: helm-repos
	helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
	  --namespace monitoring --create-namespace \
	  --set grafana.adminPassword=admin123 \
	  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
	  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false
	kubectl apply -f k8s/monitoring/podmonitor.yaml

deploy-adapter: helm-repos
	-kubectl delete configmap prometheus-adapter -n monitoring --ignore-not-found
	helm upgrade --install prometheus-adapter prometheus-community/prometheus-adapter \
	  --namespace monitoring \
	  --set prometheus.url=http://prometheus-kube-prometheus-prometheus.monitoring.svc \
	  --set prometheus.port=9090
	kubectl rollout status deployment/prometheus-adapter -n monitoring
	kubectl apply -f k8s/monitoring/adapter-apiservice.yaml
	kubectl apply -f k8s/monitoring/adapter-config.yaml
	kubectl rollout restart deployment/prometheus-adapter -n monitoring
	kubectl rollout status deployment/prometheus-adapter -n monitoring

deploy-rules:
	kubectl apply -f k8s/monitoring/prometheus-rules.yaml
	kubectl apply -f k8s/monitoring/adapter-config.yaml
	kubectl rollout restart deployment/prometheus-adapter -n monitoring

deploy-hpa:
	kubectl apply -f k8s/base/hpa.yaml

logs-a:
	kubectl logs -f -n balancit deployment/service-a

logs-b:
	kubectl logs -f -n balancit deployment/service-b

logs-otel:
	kubectl logs -f -n balancit deployment/otel-collector

logs-ml:
	kubectl logs -f -n balancit deployment/ml-service

logs-proxy:
	kubectl logs -f -n balancit deployment/proxy

restart-ml:
	kubectl rollout restart deployment/ml-service -n balancit

restart-proxy:
	kubectl rollout restart deployment/proxy -n balancit

ml-cycle: build-ml load-ml restart-ml

proxy-cycle: build-proxy load-proxy restart-proxy

forward-prometheus:
	kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090

forward-grafana:
	kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

forward-proxy:
	kubectl port-forward -n balancit svc/proxy 8080:8080

forward-a:
	kubectl port-forward -n balancit svc/service-a 8000:8000

forward-b:
	kubectl port-forward -n balancit svc/service-b 8001:8000

redis-cli:
	kubectl exec -it -n balancit deployment/redis -- redis-cli

redis-keys:
	kubectl exec -it -n balancit deployment/redis -- redis-cli KEYS '*'

redis-flush:
	kubectl exec -it -n balancit deployment/redis -- redis-cli FLUSHALL

hpa-status:
	kubectl get hpa -n balancit

status:
	@kubectl get pods -n balancit
	@echo "---"
	@kubectl get hpa -n balancit

traffic-test:
	@echo "Sending test traffic through proxy..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
	  curl -s -H "X-Client-ID: test-$$i" localhost:8080/service-a/api/cpu > /dev/null; \
	  curl -s -H "X-Client-ID: test-$$i" localhost:8080/service-a/api/light > /dev/null; \
	  curl -s -H "X-Client-ID: test-$$i" localhost:8080/service-b/api/io > /dev/null; \
	  curl -s -H "X-Client-ID: test-$$i" localhost:8080/service-b/api/slow > /dev/null; \
	done
	@echo "Done."
