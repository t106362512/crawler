kubectl create clusterrolebinding kubernetes-dashboard --clusterrole=cluster-admin --serviceaccount=kube-system:kubernetes-dashboard

kubectl apply -f https://download.elastic.co/downloads/eck/1.0.0-beta1/all-in-one.yaml 

kubectl apply -f ./stepByStep/1.createElasticsearch.yml 

#使用 kubectl get pods -w 確認 Elasticsearch 是否已建立完成
kubectl get pods -w
sleep 500

kubectl apply -f ./stepByStep/2.createKibana.yml
kubectl apply -f ./stepByStep/3.runCustomContainer.yml
kubectl apply -f ./stepByStep/4.runCustomContainer_multi.yml
PASSWORD=$(kubectl get secret seelasticsearch-es-elastic-user -o=jsonpath='{.data.elastic}' | base64 --decode)
# https://www.elastic.co/guide/en/cloud-on-k8s/current/k8s-quickstart.html#k8s_request_elasticsearch_access

kubectl get service #找到port為9200的外部ip
# curl -u 'elastic:'${PASSWORD} -k 'https://{externaleIP}:9200'