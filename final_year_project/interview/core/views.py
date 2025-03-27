import re
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpResponse
import google.generativeai as genai
from .models import User, ProgrammingSkill, Question, Response
from .forms import UserRegistrationForm, ProgrammingSkillForm, ResponseForm
import logging

# Create a logger specific to this module
logger = logging.getLogger('interview')

# Configure Gemini API
genai.configure(api_key='AIzaSyBFfemTtuUdXeSb78B-kpwLBtd9vsTPEyc')  # Replace with your key or use settings
model = genai.GenerativeModel("gemini-2.0-flash")

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = UserRegistrationForm()
    return render(request, 'registration.html', {'form': form})

def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})

@login_required
def user_logout(request):
    logout(request)
    return redirect('login')

@login_required
def home(request):
    skills = ProgrammingSkill.objects.filter(user=request.user)
    return render(request, 'home.html', {'skills': skills})

@login_required
def skill_create(request):
    if request.method == 'POST':
        form = ProgrammingSkillForm(request.POST)
        if form.is_valid():
            skill = form.save(commit=False)
            skill.user = request.user
            skill.save()
            return redirect('home')
    else:
        form = ProgrammingSkillForm()
    return render(request, 'skill_form.html', {'form': form})
import logging
import re
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)

@login_required
def start_interview(request):
    """
    Generate interview questions or handle existing interview process
    """
    # Validate user skills
    skills = ProgrammingSkill.objects.filter(user=request.user)
    
    # Early return if no skills exist
    if not skills.exists():
        logger.warning(f"User {request.user.username} has no skills defined")
        return render(request, 'home.html', {'error': 'Please add a skill first.'})
    
    # Select primary skill for interview (first skill)
    skill = skills.first()
    
    # Check existing questions
    existing_questions = Question.objects.filter(user=request.user)
    
    # Generate questions if not existing
    if not existing_questions.exists():
        max_attempts = 3  # Retry up to 3 times if insufficient questions
        questions = []
        for attempt in range(max_attempts):
            try:
                # Detailed prompt for question generation
                prompt = (
                    f"Generate interview questions for a backend {skill.language} developer with {skill.proficiency} years of experience. "
                    "Provide exactly 3 technical {skill.language} questions that test coding and problem-solving skills, "
                    "followed by exactly 3 behavioral questions assessing teamwork and professional growth. "
                    "Each question must be a clear, specific problem or scenario. "
                    "Format the questions as a list, one question per line, without numbering or introductory text. "
                    "Ensure you provide exactly 6 questions in total."
                )
                
                # Generate content using Gemini
                response = model.generate_content(
                    prompt, 
                    generation_config={
                        "temperature": 0.7, 
                        "max_output_tokens": 1000
                    }
                )
                
                # Extract raw response
                raw_response = response.candidates[0].content.parts[0].text
                logger.info(f"Attempt {attempt + 1} - Raw Gemini Response: {raw_response}")
                
                # Parse questions
                questions = [q.strip() for q in raw_response.split('\n') if q.strip()]
                
                # Filter out unwanted lines, but be less aggressive
                questions = [
                    q for q in questions
                    if len(q) > 20 and  # Ensure it's a substantial question
                    not any(x in q.lower() for x in [
                        'here are', 'following', 'generate', 'okay', 'questions for'
                    ])
                ]
                
                logger.info(f"Attempt {attempt + 1} - Parsed Questions: {questions}")
                
                # Validate questions
                if len(questions) >= 6:
                    break  # We have enough questions
                else:
                    logger.warning(f"Attempt {attempt + 1} - Insufficient questions generated: {len(questions)}")
                    if attempt == max_attempts - 1:
                        return render(request, 'home.html', {
                            'error': f'Failed to generate sufficient interview questions (only {len(questions)} generated). '
                                     'Please try again or contact support.'
                        })
            except Exception as e:
                logger.error(f"Question generation error for {request.user.username}: {str(e)}")
                return render(request, 'home.html', {
                    'error': 'An error occurred while generating interview questions. Please try again.'
                })
        
        # Create question records
        created_questions = []
        for i, question_text in enumerate(questions[:6]):
            question_type = 'technical' if i < 3 else 'behavioral'
            new_question = Question.objects.create(
                user=request.user, 
                type=question_type, 
                content=question_text, 
                skill=skill
            )
            created_questions.append(new_question)
        
        logger.info(f"Generated {len(created_questions)} questions for user {request.user.username}: {[q.content for q in created_questions]}")
    
    # Retrieve next unanswered question
    question = Question.objects.filter(
        user=request.user, 
        response__isnull=True
    ).first()
    
    # No more questions - redirect to results
    if not question:
        return redirect('interview_results')
    
    # Compute total and remaining questions
    total_questions = Question.objects.filter(user=request.user).count()
    remaining_questions = Question.objects.filter(user=request.user, response__isnull=True).count()
    current_question = total_questions - remaining_questions + 1  # Compute current question number
    
    # Handle response submission
    if request.method == 'POST':
        form = ResponseForm(request.POST)
        if form.is_valid():
            try:
                response_content = form.cleaned_data['content']
                
                # Evaluation prompt
                eval_prompt = (
                    f"Question Type: {question.type}\n"
                    f"Question: '{question.content}'\n"
                    f"Candidate's Response: '{response_content}'\n\n"
                    "Provide a detailed evaluation including:\n"
                    "1. Comprehensiveness\n"
                    "2. Technical accuracy\n"
                    "3. Problem-solving approach\n"
                    "4. Communication clarity\n"
                    "5. Numerical score (0-100%)\n"
                    "Format clearly with sections."
                )
                
                # Generate evaluation
                eval_response = model.generate_content(eval_prompt)
                evaluation = eval_response.candidates[0].content.parts[0].text
                
                # Score extraction
                try:
                    score_match = re.search(r'Score:\s*(\d+)%', evaluation)
                    score = float(score_match.group(1)) if score_match else 75.0
                except Exception:
                    score = 75.0
                
                # Create response record
                Response.objects.create(
                    question=question, 
                    content=response_content, 
                    score=score, 
                    feedback=evaluation
                )
                
                # Redirect to next question
                return redirect('start_interview')
            
            except Exception as e:
                logger.error(f"Response evaluation error: {str(e)}")
                return render(request, 'interview.html', {
                    'form': form, 
                    'question': question, 
                    'error': 'Failed to evaluate response.',
                    'total_questions': total_questions,
                    'remaining_questions': remaining_questions,
                    'current_question': current_question
                })
    else:
        # GET request: prepare form
        form = ResponseForm()
    
    # Render interview page
    return render(request, 'interview.html', {
        'form': form, 
        'question': question,
        'total_questions': total_questions,
        'remaining_questions': remaining_questions,
        'current_question': current_question
    })

@login_required
def interview_results(request):
    questions = Question.objects.filter(user=request.user)
    responses = Response.objects.filter(question__user=request.user)
    return render(request, 'results.html', {'questions': questions, 'responses': responses})