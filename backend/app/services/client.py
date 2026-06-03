import logging
import requests
from typing import List, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("hireflow.nexus")
logging.basicConfig(level=logging.INFO)

class NexusClient:
    def __init__(self):
        self.base_url = settings.NEXUS_API_BASE.rstrip("/")
        self.api_key = settings.NEXUS_API_KEY
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.2,
        primary_model: str = "gemini-2.5-flash",
        fallback_model: str = "gpt-4.1-nano"
    ) -> str:
        """
        Sends chat completion request to Nexus API. 
        If the primary model fails, falls back automatically to the fallback model.
        """
        url = f"{self.base_url}/v1/chat/completions"
        
        # 1. Attempt with primary model
        payload = {
            "model": primary_model,
            "messages": messages,
            "temperature": temperature
        }
        
        logger.info(f"Attempting LLM completion using primary model: {primary_model}")
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info("Successfully received response from primary model.")
                return content
            else:
                logger.warning(
                    f"Primary model {primary_model} failed with status {response.status_code}: {response.text}. "
                    f"Initiating fallback."
                )
        except Exception as e:
            logger.error(f"Error during primary model completion: {str(e)}. Initiating fallback.")

        # 2. Fallback attempt
        logger.info(f"Attempting LLM completion using fallback model: {fallback_model}")
        fallback_payload = {
            "model": fallback_model,
            "messages": messages,
            "temperature": temperature
        }
        try:
            response = requests.post(url, json=fallback_payload, headers=self.headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info("Successfully received response from fallback model.")
                return content
            else:
                logger.error(
                    f"Fallback model {fallback_model} failed with status {response.status_code}: {response.text}."
                )
                raise Exception(f"Nexus API call failed for both primary and fallback models. Response: {response.text}")
        except Exception as e:
            logger.critical(f"Critical error: Both models failed. Details: {str(e)}")
            # For demonstration / safety if the API is offline during development, we can return a structured dummy response
            # but let's raise the exception so standard errors can bubble up or be handled by the route caller.
            raise e

    def generate_prompt(self, system_prompt: str, user_content: str, temperature: float = 0.2) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        return self.chat_completion(messages, temperature=temperature)

nexus_client = NexusClient()
