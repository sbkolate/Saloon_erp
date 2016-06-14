# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from datetime import datetime
from frappe.utils import now
from frappe import msgprint, _
from frappe.model.mapper import get_mapped_doc
from frappe.model.naming import make_autoname
from frappe.desk.reportview import get_match_cond
from erpnext.utilities.doctype.address.address import get_address_display

class CommandFailedError(Exception):
	pass

class Appointment(Document):
	def autoname(self):
		frappe.errprint(self.customer)
		self.name = make_autoname(self.customer + '-' + '.#####')

	def validate(self):
		assign_app = frappe.db.sql("""select name,starts_on,ends_on from `tabAppointment` where status in ('Open','Confirm') 
			and ((starts_on >= '%s' and starts_on <= '%s') or (ends_on >= '%s' and ends_on <= '%s')) 
			and employee = '%s'"""%(self.starts_on, self.ends_on,self.starts_on, self.ends_on, self.employee),as_list=1)
		if assign_app:
			for app in assign_app:
				if app[0] != self.name:
					frappe.throw(_("Appointment '{0}' is already scheduled for this employee within {1} and {2}.Please change appointment time").format(assign_app[0][0], assign_app[0][1],assign_app[0][2]))

	def on_update(self):
		srvices = frappe.db.get_values("Services", {"parent":self.name}, ["item"])
		if srvices:
			lists = [s[0] for s in srvices]
			srv = ",".join(lists)
			frappe.db.sql("""update `tabAppointment` set total_services = '%s' where name = '%s' """%(srv,self.name))

@frappe.whitelist()
def get_filter_event(start, end, filters=None):
	from frappe.desk.calendar import get_event_conditions
	conditions = get_event_conditions("Appointment", filters)

	events = frappe.db.sql("""select name, employee, starts_on, ends_on, status from `tabAppointment` where((
	 	(date(starts_on) between date('%(start)s') and date('%(end)s'))
	 	or (date(ends_on) between date('%(start)s') and date('%(end)s'))
	 	or (date(starts_on) <= date('%(start)s') and date(ends_on) >= date('%(end)s')) ))
	 	%(condition)s
	 	order by starts_on """ % {
		"condition": conditions,
		"start": start,
		"end": end
		}, as_dict=1)
	return events

@frappe.whitelist()
def get_events(start, end, filters=None):
	from frappe.desk.calendar import get_event_conditions
	conditions = get_event_conditions("Appointment", filters)

	emp = frappe.db.get_all("Employee",filters={"status": "Active"},fields=["name","employee_name"])
	return emp
	
@frappe.whitelist()
def get_appointment_records(emp, start, end):
	events = frappe.db.sql("""select e.name, a.name, a.employee, a.starts_on, a.ends_on, a.status from 
			`tabEmployee` e LEFT JOIN `tabAppointment` a ON e.name = a.employee where(( 
			(date(a.starts_on) between date('%(start)s') and date('%(end)s'))
			or (date(a.ends_on) between date('%(start)s') and date('%(end)s'))
			or (date(a.starts_on) <= date('%(start)s') and date(a.ends_on) >= date('%(end)s')) )) and a.employee= ('%(emp)s') 
			order by starts_on """ % {
			"emp":emp,
			"start": start,
			"end": end
			}, as_dict=1)
	if not events:
		events = [{'status': '', 'name': 'No Appointment Scheduled', 'starts_on': start, 'ends_on': end, 'employee': emp}]
	
	return events

@frappe.whitelist()
def make_sales_invoice(source_name, target_doc=None):
	attended_by = frappe.get_value("Appointment",source_name,"employee")
	def postprocess(source, target):
		set_missing_values(source, target)

	def set_missing_values(source, target):
		target.is_pos = 1
		target.ignore_pricing_rule = 1
		[d.update({"emp":attended_by}) for d in target.get("items")]
		target.run_method("set_missing_values")

	doclist = get_mapped_doc("Appointment", source_name, {
		"Appointment": {
			"doctype": "Sales Invoice",
			"field_map": {
				"starts_on":"posting_date"
			},
			"validation": {
				"status": ["=", "Confirm"]
			}
		},
		"Services": {
			"doctype": "Sales Invoice Item",
			"field_map": {
				"item": "item_code"
			},
			"add_if_empty": True
		}

	}, target_doc, postprocess)

	return doclist


@frappe.whitelist()
def get_mob_no(doctype, txt, searchfield, start, page_len, filters):
	# company = frappe.get_value("User",frappe.session.user,"company")
	return frappe.db.sql("""select c.name, co.mobile_no from `tabCustomer` c LEFT JOIN `tabContact` co on 
		c.name = co.customer where (c.name like %(txt)s or co.mobile_no like %(txt)s) """.format(**{
		'mcond': get_match_cond(doctype)
		}), {
		'txt': "%%%s%%" % txt
	})
	# return frappe.db.sql("""select c.name, co.mobile_no from `tabCustomer` c LEFT JOIN `tabContact` co on 
	# 	c.name = co.customer where (c.name like %(txt)s or co.mobile_no like %(txt)s) 
	# 	and c.company = %(com)s """.format(**{
	# 	'mcond': get_match_cond(doctype)
	# 	}), {
	# 	'txt': "%%%s%%" % txt,
	# 	'com': company
	# })

@frappe.whitelist()
def get_customer_mobile(customer):
	return  frappe.db.sql("""select mobile_no from tabContact where customer = '%s' """ %(customer), as_list=1)

@frappe.whitelist()
def get_address(customer):
	cust_add = frappe.db.sql("""select name from tabAddress where address_title = '%s' and customer = '%s' """ %(customer,customer),as_list=1)
	if cust_add:
		address = get_address_display(cust_add[0][0])
	
		return address


@frappe.whitelist()
def create_site(args=None):
	print "in create_site------"
	site=frappe.db.sql("select domain from `tabSite master` where is_installed <>1 limit 1")
	if site:
		try:
			setup_site(site[0][0], is_active=False)
			# print "---------------------site installed updating flag ---------------------"+site[0][0]
			frappe.db.sql("update `tabSite master` set is_installed=1 where domain='%s'"%(site[0][0]))
			# print "---------------------updated site status ad installed ---------------------"+site[0][0]
			frappe.db.commit()
			#print "---------------------sending email ---------------------"+site[0][0]
			#frappe.sendmail(recipients="gangadhar.k@indictranstech.com",subject="Site '{site_name}' Created".format(site_name=site[0][0]),message="Hello gangadhar site is Created", bulk=False)
		except Exception, e:
			import traceback
			frappe.db.rollback()
			error = "%s\n%s"%(e, traceback.format_exc())
			print error	

def setup_site(domain_name, is_active=False):
	root_pwd = frappe.db.get_value("Multitenancy Settings", None, ["maria_db_root_password"])
	admin_pwd = frappe.db.get_value("Site master", domain_name, "admin_password")
	site_name = frappe.db.get_value("Multitenancy Settings", None, ["default_site"])
	#print "in setup_site ---------------"
  	cmds = [
		{
			"../bin/bench new-site --mariadb-root-password {0} --admin-password {1} {2}".format(
					root_pwd, admin_pwd, domain_name): "Creating New Site : {0}".format(domain_name)
		},
		{
			"../bin/bench use {0}".format(domain_name): "Using {0}".format(domain_name)
		},
		{ "../bin/bench install-app erpnext": "Installing ERPNext App" },
		{ "../bin/bench use {0}".format(site_name): "Setting up the default site" },
		{ "../bin/bench setup nginx": "Deploying {0}".format(domain_name) },
 		{ "sudo /etc/init.d/nginx reload": "Reloading nginx" }
	]

	for cmd in cmds:
		# print "in cmds ---------------"
		exec_cmd(cmd, cwd='../', domain_name=domain_name)

def exec_cmd(cmd_dict, cwd='../', domain_name=None):
	import subprocess
	import os
	key = cmd_dict.keys()[0]
	val = cmd_dict[key]
	cmd = "echo {desc} && {cmd}".format(desc=val, cmd=key) if val else key
	#print "executing from path ----"+os.getcwd()
	#print "executing cmd ----------  "+cmd
	#print "current user "+os.getlogin()
	p = subprocess.Popen(cmd, cwd=cwd, shell=True, stdout=None, stderr=None)
	return_code = p.wait()
	if return_code > 0:
		raise CommandFailedError("Error while executing commend : %s \n for site  : %s \n in directory %s"%(cmd, domain_name,os.getcwd()))


@frappe.whitelist()
def get_events_grid(start, end,filters=None):
	import json
	filters=json.loads(filters)
	events = frappe.db.sql("""select name, employee, employee as resource ,starts_on, ends_on, customer,
		status,0 as all_day from `tabAppointment` where %(employee_condition)s (( (date(starts_on) between 
		date('%(start)s') and date('%(end)s'))
		or (date(ends_on) between date('%(start)s') and date('%(end)s'))
		or (date(starts_on) <= date('%(start)s') and date(ends_on) >= date('%(end)s'))
		)) order by starts_on""" % {
			"start": start,
			"end": end,
			"employee_condition": " employee= '"+filters['employee']+"'  and " if filters['employee'] else ""
		}, as_dict=1)
	#frappe.errprint(events)
	
	employees=frappe.db.sql("""select name as id,employee_name  as name from tabEmployee where %(employee_condition)s  
		and status='Active' order by name """ % {
		"employee_condition": " employee= '"+filters['employee']+"' " if filters['employee'] else " '1' = 1  "
		}, as_dict=1)
	#frappe.errprint(employees)
	return events,employees

@frappe.whitelist()
def get_employees(employee=None):
	employees = frappe.db.sql("""select name as id,employee_name as name from `tabEmployee` where status='Active' 
		and %(employee_condition)s order by name""" % {	"employee_condition": " '1'=1 "	}, as_dict=1)
	# frappe.errprint(employees)
	return employees

@frappe.whitelist()
def get_payment_mode():
	mode = frappe.db.sql(""" select mode_of_payment,amount from `tabPayments` where parent='5d1a2b81c1' """, as_dict=1)
	return mode
