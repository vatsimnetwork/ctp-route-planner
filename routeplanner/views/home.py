from django.shortcuts import render

def home(request):
    return render(request, 'home.html')

home.login_not_required = True