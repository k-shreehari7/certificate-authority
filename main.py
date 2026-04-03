from fastapi import FastAPI
from fastapi.responses import FileResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
import subprocess
import argparse
import uvicorn
from pathlib import Path
import logging
from certshelper.helper_functions import (
    execute_command,
    render_template,
    create_zip,
    generate_key
)

app = FastAPI()
ROOT_CA_DIR='/root/pki/root-ca'
INTERMEDIATE_CA_DIR='/root/pki/intermediate'
DIRECTORIES_REQUIRED="mkdir -p /root/pki/root-ca/{certs,crl,newcerts,private}; mkdir -p /root/pki/intermediate/{certs,crl,csr,newcerts,private}; touch /root/pki/root-ca/index.txt /root/pki/intermediate/index.txt; echo 1000 > /root/pki/root-ca/serial; echo 1000 > /root/pki/intermediate/serial; chmod 700 /root/pki/root-ca/private /root/pki/intermediate/private; mkdir -p  /var/log/stepca; touch /var/log/stepca/stepca.log"
INITIALISE_CA_LOG_FILE='/var/log/stepca/stepca.log'

class leafcert(BaseModel):
   fqdn: str
   sans: list | None = None
 
def pre_requsites(rootcaname:str,intercaname:str) -> None:
   execute_command(DIRECTORIES_REQUIRED)  
   env = Environment(loader = FileSystemLoader('templates'))
   template = env.get_template('rootca_openssl.cnf.jinja')
   output=template.render(root_ca_path=ROOT_CA_DIR,rootca_commonname=rootcaname)
   #Render the template for the ROOT CA
   render_template('rootca_openssl.cnf.jinja',f'{ROOT_CA_DIR}/openssl.cnf',root_ca_path=ROOT_CA_DIR,rootca_commonname=rootcaname)

   #Render the template for the INTER CA
   render_template('intermediateca_openssl.cnf.jinja',f'{INTERMEDIATE_CA_DIR}/openssl.cnf',intermediate_ca_path=INTERMEDIATE_CA_DIR,interca_commonname=intercaname)


@app.get("/intialise")
def initialise_ca() -> dict:
   #Generate the key for the ROOT CA
   generate_key(f'{ROOT_CA_DIR}/private/ca.key.pem')

   #Self sign the ROOT CA certificate
   my_file = Path(f'{ROOT_CA_DIR}/certs/ca.cert.pem')

   if my_file.exists() == False:
      COMMAND=f'openssl req -config {ROOT_CA_DIR}/openssl.cnf -key {ROOT_CA_DIR}/private/ca.key.pem -new -x509 -days 3650 -sha256 -extensions v3_ca -out {ROOT_CA_DIR}/certs/ca.cert.pem'
      execute_command(COMMAND)
   else:
      logger.info("Root CA Certificate already exists,Skipping ROOT CA Certificate Generation")

   #Generate the Private Key for Intermediate CA
   generate_key(f'{INTERMEDIATE_CA_DIR}/private/intermediate.key.pem')

   #Create the CSR
   my_file=Path(f'{INTERMEDIATE_CA_DIR}/csr/intermediate.csr.pem')
   if my_file.exists() == False:
      COMMAND=f'openssl req -config {INTERMEDIATE_CA_DIR}/openssl.cnf -new -key {INTERMEDIATE_CA_DIR}/private/intermediate.key.pem -out {INTERMEDIATE_CA_DIR}/csr/intermediate.csr.pem'
      execute_command(COMMAND)
   else:
      logger.info('CSR for the Intermediate CA is already present Skipping CSR creation')

    #Sign the Intermediate with Root CA
   my_file=Path(f'{INTERMEDIATE_CA_DIR}/certs/intermediate.cert.pem')
   if my_file.exists()==False:
      COMMAND=f'openssl ca -batch -config {ROOT_CA_DIR}/openssl.cnf -extensions v3_intermediate_ca -days 1825 -notext -md sha256 -in {INTERMEDIATE_CA_DIR}/csr/intermediate.csr.pem -out {INTERMEDIATE_CA_DIR}/certs/intermediate.cert.pem'
      execute_command(COMMAND)
   else:
      logger.info('Intermediate Cert already exists, Skipping cert creation')

   my_file=Path(f'{INTERMEDIATE_CA_DIR}/certs/ca-chain.cert.pem')
   if my_file.exists()==False:
      COMMAND=f'cat {INTERMEDIATE_CA_DIR}/certs/intermediate.cert.pem {ROOT_CA_DIR}/certs/ca.cert.pem > {INTERMEDIATE_CA_DIR}/certs/ca-chain.cert.pem'
      execute_command(COMMAND)
   else:
      logger.info("Full Chain Already Exists")

   return {
      "message": "Successfully Setup the CA \n"
   }

@app.post("/generate-csr")
def generate_csr(cert:leafcert):
   fqdn = cert.fqdn
   sans = cert.sans

   logger.info(fqdn)

   
   render_template('leafcert_openssl.cnf.jinja',f'{INTERMEDIATE_CA_DIR}/{fqdn}.cnf',fqdn=fqdn,san1=sans[0],san2=sans[1])
   generate_key(f'{INTERMEDIATE_CA_DIR}/private/{fqdn}.key.pem')

   #Create the CSR for the leaf cert to be gnerate 
   csr_file = Path(f'{INTERMEDIATE_CA_DIR}/csr/{fqdn}.csr.pem')
   if csr_file.exists() == False:
      COMMAND = f'openssl req -new -key {INTERMEDIATE_CA_DIR}/private/{fqdn}.key.pem -out {INTERMEDIATE_CA_DIR}/csr/{fqdn}.csr.pem -config {INTERMEDIATE_CA_DIR}/{fqdn}.cnf'
      execute_command(COMMAND)
   else:
      logger.warning("CSR already exists in the path {INTERMEDIATE_CA_DIR}/csr/{fqdn}.csr.pem")

   zip_path = create_zip(fqdn,[f'{INTERMEDIATE_CA_DIR}/private/{fqdn}.key.pem',f'{INTERMEDIATE_CA_DIR}/csr/{fqdn}.csr.pem'])

   #Delete the conf used to Generate the Cert
   COMMAND = f'rm {INTERMEDIATE_CA_DIR}/{fqdn}.cnf'
   execute_command(COMMAND)
   return FileResponse(
      zip_path,
      media_type = "application/zip",
      filename = f'{fqdn}.zip'
   )
   
   
@app.post("/generate-certificate")
def generate_certificate(cert:leafcert):
   fqdn = cert.fqdn
   sans = cert.sans
   render_template('leafcert_openssl.cnf.jinja',f'{INTERMEDIATE_CA_DIR}/{fqdn}.cnf',fqdn=fqdn,san1=sans[0],san2=sans[1])
   generate_key(f'{INTERMEDIATE_CA_DIR}/private/{fqdn}.key.pem')

   #Create the CSR for the leaf cert to be gnerate 
   csr_file = Path(f'{INTERMEDIATE_CA_DIR}/csr/{fqdn}.csr.pem')
   if csr_file.exists() == False:
      COMMAND = f'openssl req -new -key {INTERMEDIATE_CA_DIR}/private/{fqdn}.key.pem -out {INTERMEDIATE_CA_DIR}/csr/{fqdn}.csr.pem -config {INTERMEDIATE_CA_DIR}/{fqdn}.cnf'
      execute_command(COMMAND)
   else:
      logger.warning("CSR already exists in the path {INTERMEDIATE_CA_DIR}/csr/{fqdn}.csr.pem")

   #Sign with Intermediate CA
   COMMAND = f'openssl ca -batch -config {INTERMEDIATE_CA_DIR}/openssl.cnf -extensions server_cert -days 825 -notext -md sha256 -in {INTERMEDIATE_CA_DIR}/csr/{fqdn}.csr.pem -out {INTERMEDIATE_CA_DIR}/certs/{fqdn}.cert.pem'
   execute_command(COMMAND)

   #Delete the conf used to Generate the Cert
   COMMAND = f'rm {INTERMEDIATE_CA_DIR}/{fqdn}.cnf'      
   execute_command(COMMAND)

   zip_path = create_zip(fqdn,[f'{INTERMEDIATE_CA_DIR}/private/{fqdn}.key.pem',f'{INTERMEDIATE_CA_DIR}/csr/{fqdn}.csr.pem',f'{INTERMEDIATE_CA_DIR}/certs/{fqdn}.cert.pem',f'{INTERMEDIATE_CA_DIR}/certs/ca-chain.cert.pem'])

   my_file=Path(f'{INTERMEDIATE_CA_DIR}/certs/ca-chain.cert.pem')
   if my_file.exists()==False:
      COMMAND=f'cat {INTERMEDIATE_CA_DIR}/certs/intermediate.cert.pem {ROOT_CA_DIR}/certs/ca.cert.pem > {INTERMEDIATE_CA_DIR}/certs/ca-chain.cert.pem'
      execute_command(COMMAND)
   else:
      logger.info("Full Chain Already Exists")

   return FileResponse(
      zip_path,
      media_type = "application/zip",
      filename = f'{fqdn}.zip'
   )

@app.post("/revoke")
def revoke_certificate(cert:leafcert) -> None:
   fqdn = cert.fqdn

   #Revoke the ceritificate with With FQDN
   COMMAND = f'openssl ca -config {INTERMEDIATE_CA_DIR}/openssl.cnf -revoke {INTERMEDIATE_CA_DIR}/certs/{fqdn}.cert.pem'
   execute_command(COMMAND)

   #Gen CRL list with revoked certificate
   COMMAND=f'openssl ca -config {INTERMEDIATE_CA_DIR}/openssl.cnf -gencrl -out {INTERMEDIATE_CA_DIR}/crl/intermediate.crl.pem'
   execute_command(COMMAND)
   
def get_aguemnets()->None:
   parser=argparse.ArgumentParser()
   parser.add_argument(
      '-r',
      '--rootcacn',
      help="Enter root ca common name",
      type=str,
      required=True
   )
   parser.add_argument(
      '-i',
      '--intercacn',
      help="Enter the intermediate ca common name",
      type=str,
      required=True
   )
   args=parser.parse_args()
   pre_requsites(args.rootcacn,args.intercacn)

if __name__== "__main__":
   logger = logging.getLogger(__name__)
   logger.setLevel("DEBUG")

   formatter = logging.Formatter("{asctime} - {levelname} - {message}", style="{")

   console_handler = logging.StreamHandler()
   console_handler.setLevel("INFO")
   console_handler.setFormatter(formatter)
   logger.addHandler(console_handler)
   file_handler = logging.FileHandler(INITIALISE_CA_LOG_FILE,mode="a",encoding="utf-8")
   file_handler.setLevel("DEBUG")
   file_handler.setFormatter(formatter)
   logger.addHandler(file_handler)
   get_aguemnets()
   uvicorn.run(app, host="127.0.0.1", port=8000)
