import sys
import subprocess
from pathlib import Path
import logging
from jinja2 import Environment, FileSystemLoader

import os
import zipfile

logger = logging.getLogger(__name__)
def execute_command(cmd:str) -> None:
   try:
      subprocess.run(cmd,shell=True,check=True)
      logger.info(f'Successfully executed the command {cmd}')
   except subprocess.CalledProcessError as exe:
      logger.error(f'Failed to execute the command {cmd} with Error Code {exe}')
      sys.exit()

def render_template(file:str,output_file,**kwargs: any ) -> None:
   env = Environment(loader = FileSystemLoader('templates'))
   template = env.get_template(file)

   output = template.render(kwargs)
   with open(f"{output_file}", 'w') as f:
      print(output,file=f)
    
def create_zip(fqdn:str,file_paths: list | None = None):
   zip_path = f'/tmp/{fqdn}.zip'

   with zipfile.ZipFile(zip_path,"w") as zip_file:
      for file_path in file_paths:
         zip_file.write(file_path,arcname=os.path.basename(file_path))
   return zip_path

def generate_key(file_path:str) -> None:
   key_file = Path(file_path)
   
   if key_file.exists() == False:
      COMMAND=f'openssl genpkey -algorithm RSA -out {file_path} -pkeyopt rsa_keygen_bits:4096'
      execute_command(COMMAND)
   else:
      logger.warning("Private key already exists , skipping the key creation")