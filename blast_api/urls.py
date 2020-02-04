from django.urls import include, path

from . import views

urlpatterns = [
    path('shouts/<int:shout_id>;cancel', views.cancel_shout, name='cancel_shout'),
    path('shouts/<int:shout_id>', views.get_shout, name='get_shout'),
    path('shouts', views.shouts, name='shouts'),
    path('calls', views.calls, name='calls'),
    path('dnc/<str:userdata>', views.dnc, name='dnc'),
    path('dnc/<str:userdata>/<str:number>', views.dnc_delete, name='delete_dnc'),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
]
