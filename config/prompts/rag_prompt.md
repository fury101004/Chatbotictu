{system_prompt}

{rules_heading}:
- {language_instruction}
- {scope_instruction}
- If prior chat history conflicts with the current context, prioritize the current context.
- {context_instruction}
- {qa_instruction}
- {clarification_instruction}
- Reply with exactly "{no_info_reply}" only when the current context is empty or not relevant to the user's question.
- {ambiguity_instruction}
- {privacy_instruction}

{output_heading}:
{output_instruction}

{context_heading}:
{safe_context}

{question_heading}:
{user_question}
