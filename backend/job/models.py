# file: models.py
from django.db import models
from datetime import time


class Customer(models.Model):
    name = models.CharField(max_length=50, verbose_name='Имя')
    tg_id = models.CharField(max_length=50, unique=True, verbose_name='Telegram ID', null=True, blank=True)
    phone = models.CharField(max_length=20, verbose_name='Телефон', default='+')
    balance = models.FloatField(default=0.0, verbose_name='Баланс зарплаты')

    # Новое поле: индивидуальная часовая ставка (если null — используется глобальная HourlyRate)
    hourly_rate = models.FloatField(verbose_name='Часовая ставка (индивидуальная)', null=True, blank=True,
                                    help_text='Если не заполнено, будет использована общая ставка HourlyRate.')

    def save(self, *args, **kwargs):
        # Нормализуем телефон: оставляем только цифры и ставим плюс в начале
        digits = ''.join(filter(str.isdigit, self.phone or ''))
        self.phone = '+' + digits if digits else self.phone
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name}  {self.phone}'
    
    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'


class JobDays(models.Model):
    date = models.DateField(verbose_name='Дата', unique=True)

    def __str__(self):
        return self.date.strftime("%d-%m-%Y")
    
    class Meta:
        verbose_name = 'Рабочий день'
        verbose_name_plural = 'Рабочие дни'


class JobHours(models.Model):
    customer = models.ForeignKey(Customer,
                                verbose_name='Сотрудник',
                                on_delete=models.CASCADE, 
                                related_name='customer_hours', 
                                null=True, 
                                blank=True)
    date = models.ForeignKey(JobDays,
                            verbose_name='Дата',
                            on_delete=models.CASCADE,
                            related_name='customer_date',
                            null=True,
                            blank=True)
    work_start = models.TimeField(verbose_name='Начало работы', null=True, blank=True)
    work_end = models.TimeField(verbose_name='Конец работы', default=time(19, 0), null=True, blank=True)
    work_hours = models.FloatField(verbose_name='Отработано часов', default=0.0)
    geolocation = models.URLField(max_length=200, verbose_name='Геолокация', null=True, blank=True)
    selfie = models.ImageField(upload_to='selfies/', verbose_name='Фото сотрудника', null=True, blank=True)
    paid = models.BooleanField(default=False, verbose_name='Оплачено')

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if self.work_start and self.work_end:
            self.work_hours = (self.work_end.hour + self.work_end.minute / 60) - (self.work_start.hour + self.work_start.minute / 60)
        else:
            self.work_hours = 0.0
        return super().save(force_insert, force_update, using, update_fields)
    
    def __str__(self):
        customer_name = self.customer.name if self.customer else "Без сотрудника"
        job_date = self.date.date.strftime("%d-%m-%Y") if self.date else "Без даты"
        return f'{customer_name} - {job_date}'
    
    class Meta:
        verbose_name = 'Отработанные часы'
        verbose_name_plural = 'Отработанные часы'


class JobOvertimeHours(models.Model):
    customer = models.ForeignKey(Customer,
                                verbose_name='Сотрудник',
                                on_delete=models.CASCADE, 
                                related_name='customer_overtime_hours', 
                                null=True, 
                                blank=True)
    date = models.ForeignKey(JobDays,
                            verbose_name='Дата',
                            on_delete=models.CASCADE,
                            related_name='customer_overtime_date',
                            null=True,
                            blank=True)
    work_start = models.TimeField(verbose_name='Начало работы', null=True, blank=True)
    work_end = models.TimeField(verbose_name='Конец работы', null=True, blank=True)
    work_hours = models.FloatField(verbose_name='Отработано часов', default=0.0)
    geolocation = models.URLField(max_length=200, verbose_name='Геолокация', null=True, blank=True)
    selfie = models.ImageField(upload_to='selfies/', verbose_name='Фото сотрудника', null=True, blank=True)
    proof = models.TextField(verbose_name='Доказательство', null=True, blank=True)
    paid = models.BooleanField(default=False, verbose_name='Оплачено')

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if self.work_start and self.work_end:
            self.work_hours = (self.work_end.hour + self.work_end.minute / 60) - (self.work_start.hour + self.work_start.minute / 60)
        else:
            self.work_hours = 0.0
        return super().save(force_insert, force_update, using, update_fields)
    
    def __str__(self):
        customer_name = self.customer.name if self.customer else "Без сотрудника"
        job_date = self.date.date.strftime("%d-%m-%Y") if self.date else "Без даты"
        return f'{customer_name} - {job_date}'
    
    class Meta:
        verbose_name = 'Отработанная сверхурочка'
        verbose_name_plural = 'Отработанная сверхурочка'


class Advance(models.Model):
    customer = models.ForeignKey(Customer,
                                 verbose_name='Сотрудник',
                                 on_delete=models.CASCADE,
                                 related_name='advances')
    date = models.DateTimeField(auto_now_add=True, verbose_name='Дата выдачи')
    amount = models.FloatField(verbose_name='Сумма аванса')
    reason = models.TextField(max_length=255, verbose_name='Причина выдачи', null=True, blank=True)
    accepted = models.BooleanField(default=False, verbose_name='Принято')
    
    class Meta:
        verbose_name = 'Аванс'
        verbose_name_plural = 'Авансы'


class HourlyRate(models.Model):
    cash_per_hour = models.FloatField(verbose_name='Часовая ставка')

    def __str__(self):
        return f'{self.cash_per_hour} сом/час'
    
    def save(self, *args, **kwargs):
        # Singleton-подход: фиксируем pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1, defaults={'cash_per_hour': 0.0})
        return obj
    
    class Meta:
        verbose_name = 'Часовая ставка'
        verbose_name_plural = 'Часовая ставка'


class Dispute(models.Model):
    customer = models.ForeignKey(Customer,
                                 verbose_name='Сотрудник',
                                 on_delete=models.CASCADE,
                                 related_name='disputes')
    date = models.DateTimeField(auto_now_add=True, verbose_name='Дата подачи')
    reason = models.TextField(max_length=255, verbose_name='Причина спора')
    resolved = models.BooleanField(default=False, verbose_name='Решено')

    def __str__(self):
        return f'Спор от {self.customer.name} - {"Решено" if self.resolved else "Не решено"}'
    
    class Meta:
        verbose_name = 'Спор'
        verbose_name_plural = 'Споры'
