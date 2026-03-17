# Repository to collect my experiments with AI

So far, I've been playing with RAG to help using local LLMs to answer questions about my codebase in Java. Other languages are not supported yet.
I tried using Gemini first to get the RAG fully implemented. I got it working however the results are quite bad. I need more troubleshoting on it but basically it doesn't find the right context to answer the questions.

Then I tried building the same RAG but using Claude. It works way better. I can get real answers using the same models I used on the tests in the Gemini RAG.

The difference on the behavior makes me believe the problem with what Gemini gave me is on the prompt engineering side. I'll try to improve it and see if I can get better results.

I don't have a powerful hardware so I'm models with max 19GB, Q4 quantization and 4bit precision, from 9B to 30B parameters.

Each experiment has setup and running guides.
