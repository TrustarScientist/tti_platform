from django.shortcuts import render

# Create your views here.
def index(request):
    return render(request, 'index.html')

# dashboard view that redirects users to their respective dashboards based on their user type
def dashboard(request):
    user = request.user
    if user.is_authenticated:
        if user.role == 'admin':
            return render(request, 'admin_dashboard.html')
        elif user.role == 'school_partner':
            return render(request, 'dashboard/dashboard_school_partner.html')
        elif user.role == 'parent':
            return render(request, 'dashboard/dashboard_parent.html')
        elif user.role == 'instructor':
            return render(request, 'dashboard/dashboard_instructor.html')
        elif user.role == 'student':
            return render(request, 'dashboard/dashboard_student.html')                                            
        else:
            # If the user type is not recognized, redirect to a default page or show an error
            return render(request, 'dashboard_error.html')
    else:
        # If the user is not authenticated, redirect to the login page
        return render(request, 'auth/login.html')

