import stripe
stripe.PaymentIntent.create(amount=1000)
from openai import OpenAI
c = OpenAI()
